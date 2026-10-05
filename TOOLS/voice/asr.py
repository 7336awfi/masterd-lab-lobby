#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MasterD 语音系统 · ASR（你说 → 我听懂）
========================================
用途：手机录音 → 传上来 → 转成文字 → 给我（解决"打字易错"）

技术：智谱 ASR（glm-4-voice / audio/transcriptions）
     ★ 智谱端点已验证可用（401/500 = 要认证/要音频，不是404）

用法：
  python3 asr.py <audio_file>        # 转文字
  python3 asr.py --selftest          # 自检
"""
import os
import sys
import json
import base64
import urllib.request
from pathlib import Path

ZHIPU_URL = os.environ.get("ZHIPU_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_KEY = os.environ.get("ZHIPU_KEY", "")
ASR_MODEL = os.environ.get("MD_ASR_MODEL", "glm-asr")   # 智谱语音识别模型


def transcribe(audio_path: str) -> dict:
    """把音频转文字。支持 wav/mp3。"""
    p = Path(audio_path)
    if not p.exists():
        return {"ok": False, "error": f"文件不存在: {audio_path}"}
    if not ZHIPU_KEY:
        return {"ok": False, "error": "无 ZHIPU_KEY"}

    audio_b64 = base64.b64encode(p.read_bytes()).decode()
    # 智谱 ASR：multipart 或 base64 二选一，先用 base64 试
    payload = {
        "model": ASR_MODEL,
        "file": audio_b64,
        "file_type": p.suffix.lstrip(".") or "wav",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{ZHIPU_URL}/audio/transcriptions",
        data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {ZHIPU_KEY}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
        text = resp.get("text") or resp.get("result") or resp.get("data", {}).get("text", "")
        return {"ok": True, "text": text, "raw": resp}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        print("ZHIPU_URL:", ZHIPU_URL)
        print("ASR_MODEL:", ASR_MODEL)
        print("KEY:", "已配置" if ZHIPU_KEY else "❌ 缺")
        print("可用" if ZHIPU_KEY else "不可用")
    elif len(sys.argv) > 1:
        print(json.dumps(transcribe(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        print("用法: python3 asr.py <audio.mp3|wav> | --selftest")
