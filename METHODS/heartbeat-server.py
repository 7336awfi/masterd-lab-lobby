"""
带心跳的思考服务（Heartbeat Thinking Service）

问题（DeepSeek 点破）：
    思考久 → 网关/客户端"多久没收到数据"就判超时 → "一直连接中"
解法：
    思考时也"持续吐字节"（心跳），让网关知道"它还活着"

本模块演示「心跳保活」的实现：
    · 收到请求 → 立即返回"开始思考"
    · 每 N 秒发一个心跳（"还在思考..."）
    · 思考完成 → 发结果

两种实现：
    A. 流式（SSE）—— 真流式，推荐
    B. 心跳线程 —— 简单版（长轮询配合）

用法：
    # 作为服务跑
    python3 heartbeat_server.py

    # 测试
    curl -N http://localhost:28300/think?q=你好
"""

import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("MD_HB_PORT", "28300"))
RELAY = os.environ.get("MD_RELAY", "http://localhost:28080")
TOKEN = os.environ.get("MD_RELAY_TOKEN", "abc123xyz789test")
HEARTBEAT_INTERVAL = int(os.environ.get("MD_HB_INTERVAL", "10"))


def think_slow(question: str) -> str:
    """调用大模型（可能慢）。"""
    payload = {
        "provider": "deepseek",
        "messages": [{"role": "user", "content": question[:2000]}],
        "temperature": 0.7,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{RELAY}/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/think"):
            self._think_stream()
        elif self.path == "/health":
            self._json(200, {"ok": True, "service": "heartbeat"})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _think_stream(self):
        """
        带心跳的流式响应（SSE）。
        ★ 关键：思考期间，每 HEARTBEAT_INTERVAL 秒发一个 heartbeat，
           让网关知道"连接还活着"，不判超时。
        """
        q = parse_qs(urlparse(self.path).query)
        question = (q.get("q") or ["你好"])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # 让 nginx 不缓冲
        self.end_headers()

        # 结果容器
        result = {"text": None, "done": False, "error": None}

        def worker():
            try:
                result["text"] = think_slow(question)
            except Exception as e:
                result["error"] = repr(e)
            finally:
                result["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # ★ 心跳循环：每 N 秒发一次，直到思考完成
        start = time.time()
        while not result["done"]:
            # 发心跳
            hb = {"type": "heartbeat",
                  "elapsed": round(time.time() - start, 1),
                  "ts": datetime.now(timezone.utc).isoformat()}
            try:
                self.wfile.write(f"data: {json.dumps(hb, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return  # 客户端断了
            # 等待（分片睡，以便及时响应完成）
            for _ in range(HEARTBEAT_INTERVAL * 10):
                if result["done"]:
                    break
                time.sleep(0.1)

        # 发结果
        if result["error"]:
            out = {"type": "error", "error": result["error"]}
        else:
            out = {"type": "result", "text": result["text"],
                   "elapsed": round(time.time() - start, 1)}
        try:
            self.wfile.write(f"data: {json.dumps(out, ensure_ascii=False)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    print(f"心跳思考服务启动: http://0.0.0.0:{PORT}")
    print(f"测试: curl -N 'http://localhost:{PORT}/think?q=你好'")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
