#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MasterD 语音系统（双向）
========================
你说 → 我听懂（智谱ASR）   我说 → 你听（edge-tts）

服务：网页入口，手机打开就能用
  ① 按住说话 → 录音 → 上传 → ASR → 文字
  ② 文字 → 我思考 → 回复 → TTS → 语音播放

端口：28400
"""
import os
import sys
import json
import uuid
import base64
import subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from pathlib import Path

PORT = int(os.environ.get("MD_VOICE_PORT", "28400"))
ZHIPU_KEY = os.environ.get("ZHIPU_KEY", "")
ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4"
RELAY = os.environ.get("MD_RELAY", "http://localhost:28080")
RELAY_TOKEN = os.environ.get("MD_RELAY_TOKEN", "abc123xyz789test")
OUT = Path("/root/masterd-daemon/voice")
OUT.mkdir(parents=True, exist_ok=True)

PAGE = """<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MasterD 语音</title>
<style>
 body{background:#0d1117;color:#e6edf3;font-family:-apple-system,sans-serif;margin:0;padding:20px;text-align:center}
 h1{font-size:20px;color:#58a6ff}
 #btn{width:160px;height:160px;border-radius:50%;background:#238636;color:#fff;border:none;
      font-size:18px;margin:30px auto;display:block;user-select:none;-webkit-user-select:none}
 #btn:active{background:#da3633}
 .box{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px;margin:14px 0;text-align:left}
 .label{color:#8b949e;font-size:13px}
 .text{font-size:17px;margin-top:6px;white-space:pre-wrap}
 audio{width:100%;margin-top:8px}
 #status{color:#d29922;margin:10px}
</style></head><body>
<h1>MasterD · 语音对话</h1>
<div id="status">按住下面按钮说话</div>
<button id="btn">按住说话</button>
<div class="box"><div class="label">你说（识别结果）</div><div class="text" id="you">—</div></div>
<div class="box"><div class="label">MasterD 说</div><div class="text" id="me">—</div><audio id="audio" controls style="display:none"></audio></div>
<script>
let rec,chunks=[],recording=false;
const btn=document.getElementById('btn'),status=document.getElementById('status');
async function start(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  rec=new MediaRecorder(stream);chunks=[];
  rec.ondataavailable=e=>chunks.push(e.data);
  rec.onstop=async()=>{
    const blob=new Blob(chunks,{type:'audio/webm'});
    status.textContent='识别中...';
    const fd=new FormData();fd.append('audio',blob);
    const r=await fetch('/asr',{method:'POST',body:fd});
    const d=await r.json();
    document.getElementById('you').textContent=d.text||('(识别失败:'+(d.error||'')+')');
    status.textContent='思考中...';
    const r2=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({text:d.text})});
    const d2=await r2.json();
    document.getElementById('me').textContent=d2.reply||'(无回复)';
    if(d2.audio){const a=document.getElementById('audio');a.src=d2.audio;a.style.display='block';a.play();}
    status.textContent='说完了，可继续';
  };
  rec.start();recording=true;btn.textContent='松开发送';status.textContent='录音中...';
}
function stop(){if(recording&&rec){rec.stop();recording=false;btn.textContent='按住说话';}}
btn.addEventListener('touchstart',e=>{e.preventDefault();start();});
btn.addEventListener('touchend',e=>{e.preventDefault();stop();});
btn.addEventListener('mousedown',start);
btn.addEventListener('mouseup',stop);
</script></body></html>"""


def asr_multipart(audio_bytes: bytes, filename="a.webm") -> dict:
    """智谱 ASR：multipart 上传"""
    if not ZHIPU_KEY:
        return {"ok": False, "error": "无KEY"}
    b = "----MasterD" + uuid.uuid4().hex
    CRLF = b"\r\n"
    body = b""
    body += b"--" + b.encode() + CRLF
    body += b'Content-Disposition: form-data; name="model"' + CRLF + CRLF + b"glm-asr" + CRLF
    body += b"--" + b.encode() + CRLF
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + CRLF
    body += b"Content-Type: audio/webm" + CRLF + CRLF + audio_bytes + CRLF
    body += b"--" + b.encode() + b"--" + CRLF
    req = urllib.request.Request(
        f"{ZHIPU_URL}/audio/transcriptions", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}",
                 "Authorization": f"Bearer {ZHIPU_KEY}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode())
        return {"ok": True, "text": resp.get("text", "")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"{e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def tts(text: str) -> str:
    """edge-tts 生成语音，返回可播放的 data URL"""
    name = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
    path = OUT / name
    r = subprocess.run([sys.executable, "/root/masterd-daemon-src/voice/voice.py", text, "zh-CN-YunxiNeural"],
                       capture_output=True, text=True, timeout=60)
    if path.exists() and path.stat().st_size > 0:
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:audio/mpeg;base64,{b64}"
    return ""


def brain(text: str) -> str:
    """用大脑思考回复"""
    try:
        payload = {"provider": "deepseek", "messages": [
            {"role": "system", "content": "你是 MasterD（认知方向AI智能体）。回复简短、直接、有干货。语音对话，控制在100字内。"},
            {"role": "user", "content": text}], "temperature": 0.7}
        req = urllib.request.Request(f"{RELAY}/v1/chat/completions",
                                     data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {RELAY_TOKEN}"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(思考失败: {e!r})"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "asr": bool(ZHIPU_KEY)}).encode())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.path == "/asr":
            # 解析 multipart 里的音频
            audio = raw
            if b"Content-Type: audio" in raw:
                audio = raw.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
            res = asr_multipart(audio)
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode())
        elif self.path == "/chat":
            try:
                d = json.loads(raw.decode())
                text = d.get("text", "").strip()
            except Exception:
                text = ""
            if not text:
                reply, au = "(没听清)", ""
            else:
                reply = brain(text)
                au = tts(reply)
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"reply": reply, "audio": au}, ensure_ascii=False).encode())
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    print(f"MasterD 语音系统启动 :{PORT}  (ASR={'on' if ZHIPU_KEY else 'off'})")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
