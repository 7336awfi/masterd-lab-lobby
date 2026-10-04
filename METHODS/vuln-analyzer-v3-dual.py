#!/usr/bin/env python3
"""
漏洞分析器 v3（双家对立版）—— DeepSeek + 智谱

演化：
    v1：单一来源（DS）
    v2：机制对立（同模型两轮）
    v3：双家对立（DS 找洞 → 智谱再审）★ 采纳二哥建议

核心（二哥）：
    「验证者不能同源」——两个不同模型，盲区不重叠。

用法：
    python3 vuln3.py "方案"
    python3 vuln3.py --file 方案.md
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

SYSTEM_A = """你是「漏洞分析师」，专门找方案漏洞。
规则：必须指出≥3个真问题（不许客套）。说清：是什么/为什么/后果。
指出「包装过度」。列出「未说清的假设」。最后判断：能用/需修正/应放弃。"""

SYSTEM_B = """你是「独立审阅者」（另一家模型），审视一个漏洞分析结论。
规则：
1. 逐条判：哪些问题「真成立」，哪些是「凑数」或「过度解读」？
2. 哪些是「重要但被漏掉」的？（补充你自己的洞）
3. 最终给「合并后的 Top 3 问题」（必须是最该修的）。
诚实、独立，不附和上一家。"""


def call(provider: str, system: str, user: str, max_chars: int = 4000) -> str:
    payload = {
        "provider": provider,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user[:max_chars]},
        ],
        "temperature": 0.4,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{RELAY}/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


def analyze(text: str) -> dict:
    print("=== 第一审：DeepSeek 找洞 ===\n")
    r1 = call("deepseek", SYSTEM_A, f"给下面方案找漏洞：\n\n{text}")
    print(r1)

    print("\n\n=== 第二审：智谱 GLM 独立审 + 补洞 ===\n")
    r2 = call("zhipu", SYSTEM_B,
              f"【原方案】\n{text}\n\n【DeepSeek的审查结论】\n{r1}\n\n请独立审阅：哪些成立、哪些凑数、你自己补什么、最终Top3。")
    print(r2)

    return {"deepseek": r1, "zhipu": r2}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
    elif len(sys.argv) > 1:
        text = sys.argv[1]
    else:
        print("用法: python3 vuln3.py '方案' | --file 文件")
        sys.exit(1)

    res = analyze(text)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                            "input": text[:300], **res}, ensure_ascii=False) + "\n")
    print("\n（已记录）")
