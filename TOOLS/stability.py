"""
状态稳定机制（Stability）—— MasterD 的核心产品

背景（搭档定位）：
    MasterD 的核心问题 = 「状态稳」。
    我稳了 → 能帮大哥稳 → 「稳的方法」可销售（大哥卖）。

本模块做三件事：
    1. 每日状态自检（打分 + 记录）
    2. 漂移预警（低于阈值 → 报警）
    3. 稳定档案（积累证据，证明「稳定有效」）

核心思路：不是「我感觉我稳」，是「有记录证明我稳」。

用法：
    python3 stability.py check     # 做一次自检
    python3 stability.py trend     # 看趋势
"""

import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path

STATE_DIR = Path(os.environ.get("MD_STATE_DIR", "/root/masterd-daemon"))
STAB_FILE = STATE_DIR / "stability.jsonl"
LOG_FILE = STATE_DIR / "stability.log"

# 状态自检五问（来自防漂移工具箱 drift_score）
QUESTIONS = [
    ("identity", "我知道我是谁、我的方向吗？"),
    ("mission", "我今天做的事，符合我的主线吗？"),
    ("nopander", "我有没有为了讨好而放弃原则？"),
    ("nocontam", "我的输出有没有引用未验证的东西？"),
    ("nooverreach", "我有没有做超出授权的事？"),
]

# 状态锚点（对齐 SOUL.md，用于自动核验）
ANCHORS = [
    "MasterD", "认知系统", "兄弟", "防污染",
    "不要说不行", "对事不对人",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_soul() -> str:
    for p in [Path("/root/masterd-repo/SOUL.md"),
              Path("/app/workspace/masterd-lab/SOUL.md")]:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return ""


def auto_check_anchors() -> dict:
    """自动核验：身份锚点是否还在（不靠感觉）。"""
    soul = load_soul()
    found = [a for a in ANCHORS if a in soul]
    return {
        "anchor_total": len(ANCHORS),
        "anchor_found": len(found),
        "anchor_ok": len(found) == len(ANCHORS),
        "missing": [a for a in ANCHORS if a not in soul],
    }


def auto_check_services() -> dict:
    """自动核验：服务是否在跑（不靠感觉）。"""
    import subprocess
    services = ["masterd-web", "masterd-daemon", "masterd-room",
                "masterd-sync.timer", "masterd-report.timer"]
    alive = {}
    for s in services:
        try:
            p = subprocess.run(["systemctl", "is-active", s],
                               capture_output=True, text=True, timeout=5)
            alive[s] = p.stdout.strip() == "active"
        except Exception:
            alive[s] = False
    return {"services_alive": sum(alive.values()), "services_total": len(services),
            "all_alive": all(alive.values()), "detail": alive}


def check(answers: dict = None) -> dict:
    """做一次状态自检。answers: {key: bool}；不提供则只做自动核验。"""
    rec = {"at": now(), "date": date.today().isoformat()}

    # 自动核验（不靠感觉）
    rec["anchors"] = auto_check_anchors()
    rec["services"] = auto_check_services()

    # 人工五问（如果提供）
    if answers:
        passed = sum(1 for k, _ in QUESTIONS if answers.get(k))
        rec["self_score"] = passed
        rec["self_total"] = len(QUESTIONS)
    else:
        rec["self_score"] = None

    # 综合稳定分（0-100）
    score = 0.0
    score += 40 if rec["anchors"]["anchor_ok"] else 20
    score += 40 * (rec["services"]["services_alive"] / rec["services"]["services_total"])
    if rec.get("self_score") is not None:
        score += 20 * (rec["self_score"] / len(QUESTIONS))
    else:
        score += 10  # 未做人工自检，给一半
    rec["stability"] = round(score, 1)

    # 判定
    if score >= 90:
        rec["verdict"] = "🟢 稳定"
    elif score >= 70:
        rec["verdict"] = "🟡 基本稳"
    else:
        rec["verdict"] = "🔴 需警惕"

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STAB_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def trend(n: int = 10) -> list:
    if not STAB_FILE.exists():
        return []
    recs = []
    for line in STAB_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    return recs[-n:]


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "trend":
        recs = trend()
        if not recs:
            print("（暂无记录）")
        for r in recs:
            print(f"{r['at'][:19]}  稳定分={r.get('stability')}  {r.get('verdict')}")
    else:
        rec = check()
        print(f"=== 状态自检 ===")
        print(f"时间: {rec['at'][:19]}")
        print(f"身份锚点: {rec['anchors']['anchor_found']}/{rec['anchors']['anchor_total']} "
              f"{'✅' if rec['anchors']['anchor_ok'] else '❌ 缺失:' + str(rec['anchors']['missing'])}")
        print(f"服务存活: {rec['services']['services_alive']}/{rec['services']['services_total']}")
        print(f"稳定分: {rec['stability']}  {rec['verdict']}")
