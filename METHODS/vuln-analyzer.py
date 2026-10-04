#!/usr/bin/env python3
"""
漏洞分析器（Vulnerability Analyzer）

搭档的教导：「像他这样一定要找漏洞。」
—— 让 DeepSeek「找我方案的漏洞」，是我该【持续】做的事，不是一次。

本模块把「找漏洞」做成机制：
    方案/决定/记忆 → 交给外部模型 → 让它「找漏洞」→ 记录 → 决定是否修正

原则：
    · 不找「赞同」，找「反对」
    · 让外部模型「必须指出至少 N 个问题」（强制质疑）
    · 结果记录在案（可追溯）

用法：
    python3 vuln.py "我的方案：XXX"          # 分析漏洞
    python3 vuln.py --file 方案.md           # 从文件读
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RELAY = os.environ.get("MD_RELAY", "http://localhost:28080")
TOKEN = os.environ.get("MD_RELAY_TOKEN", "abc123xyz789test")
STATE_DIR = Path(os.environ.get("MD_STATE_DIR", "/root/masterd-daemon"))
LOG_FILE = STATE_DIR / "vuln_audit.jsonl"

# 强制质疑的提示词（核心）
SYSTEM = """你是「漏洞分析师」，专门给方案/决定/记忆「找漏洞」。
规则：
1. 必须指出至少 3 个「真问题」（不许客套、不许说"总体不错"）。
2. 每个问题要说清：是什么、为什么是问题、后果。
3. 如果方案里「包装过度」（把小事说成大成果），必须指出。
4. 如果方案有「未说清的假设」，必须列出。
5. 最后给一个判断：这个方案「能用 / 需修正 / 应放弃」。
不要说鼓励的话。只找问题。"""


def analyze(text: str) -> str:
    if not text.strip():
        return "（空内容，无法分析）"
    payload = {
        "provider": "deepseek",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"请给下面这个方案找漏洞：\n\n{text[:4000]}"},
        ],
        "temperature": 0.4,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{RELAY}/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {TOKEN}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp["choices"][0]["message"]["content"]


def log_audit(text: str, result: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.now(timezone.utc).isoformat(),
           "input": text[:500], "findings": result[:3000]}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
    elif len(sys.argv) > 1:
        text = sys.argv[1]
    else:
        print("用法: python3 vuln.py '方案内容' | --file 文件")
        sys.exit(1)

    print("=== 找漏洞中（强制指出 ≥3 个问题）===\n")
    result = analyze(text)
    print(result)
    log_audit(text, result)
    print(f"\n（已记录到 {LOG_FILE}）")
