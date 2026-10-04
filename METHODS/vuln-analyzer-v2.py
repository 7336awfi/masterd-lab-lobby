#!/usr/bin/env python3
"""
漏洞分析器 v2（机制对立版）

v1 → v2 的变化（采纳二哥建议）：
    v1：单一来源（只听 DeepSeek）→ 假验证风险
    v2：机制对立（同一模型，角色切换 + 双轮质疑）

核心认知（二哥）：
    「你缺的不是第二个模型，是对立的机制。」
    「用钱代替设计」= 懒。

三个机制（0 成本）：
    ① 角色对立：同一模型切成"批判者"
    ② 双轮质疑：第二轮问"你说的问题，哪里可能说错？"
    ③ 结构化提问："3个失败场景""最坏情况"

用法：
    python3 vuln2.py "方案内容"
    python3 vuln2.py --file 方案.md
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

# 第一轮：批判者
SYSTEM_CRITIC = """你是「漏洞分析师」，专门给方案/决定「找漏洞」。
规则：
1. 必须指出至少 3 个「真问题」（不许客套、不许说"总体不错"）。
2. 每个问题说清：是什么、为什么是问题、后果。
3. 如果方案「包装过度」（把小事说成大成果），必须指出。
4. 列出「未说清的假设」。
5. 最后判断：能用 / 需修正 / 应放弃。
不说鼓励的话。只找问题。"""

# 第二轮：质疑自己（防"凑数"和"过度找洞"）
SYSTEM_META = """你是「元审员」，审视上一个审查者的结论。
规则：
1. 审查者列了 N 个问题——逐条问：这些问题「真的成立」吗？哪些是「凑数」？
2. 哪些问题「过度解读」了？（把"未定义"说成"缺陷"）
3. 哪些是「真问题」，哪些是「假设问题」（假设成立才成立）？
4. 最后：如果只能保留 3 个问题，是哪 3 个？
诚实，不客套。"""


def call(system: str, user: str, max_chars: int = 4000) -> str:
    payload = {
        "provider": "deepseek",
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
    """机制对立：两轮。"""
    # 第一轮：找洞
    print("=== 第一轮：找漏洞（批判者）===\n")
    round1 = call(SYSTEM_CRITIC, f"给下面这个方案找漏洞：\n\n{text}")
    print(round1)

    # 第二轮：质疑第一轮（防凑数）
    print("\n\n=== 第二轮：质疑第一轮（元审）===\n")
    round2 = call(
        SYSTEM_META,
        f"【原方案】\n{text}\n\n【第一轮审查结论】\n{round1}\n\n请质疑第一轮的结论。")
    print(round2)

    return {"round1": round1, "round2": round2}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        text = Path(sys.argv[2]).read_text(encoding="utf-8")
    elif len(sys.argv) > 1:
        text = sys.argv[1]
    else:
        print("用法: python3 vuln2.py '方案' | --file 文件")
        sys.exit(1)

    res = analyze(text)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                            "input": text[:300], **res}, ensure_ascii=False) + "\n")
    print(f"\n（已记录）")
