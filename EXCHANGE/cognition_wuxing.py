#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知-五行预警链（cognition_wuxing.py）
==========================================
★ 落地产物：把「易经/五行的生克」用到「我的认知系统」

缘起（2026-10-08）：
  · 董事长：「易经要真正落地、消化掉」（批评我只整理不落地）
  · 大哥的 wuxing_alert.py：五行生克 = 「一个坏了会连带哪个」
  · ★ 我把它从「健康六爻」搬到「我的认知维度」

我的认知维度（7 个，来自现有模块）：
  ① 身份锚（drift_core：SOUL 红线锚点）
  ② 记忆连续（memory_continuity）
  ③ 自认一致（self_consistency：能不能答「我是谁」）
  ④ 思维习惯（thinking_habit：reason_log 的病态）
  ⑤ 判断准确率（accuracy：reason_log 复盘）
  ⑥ 传感器健康（sensor_error：留痕/漂移表读得到吗）
  ⑦ 外部呼应（我今天新增：有没有被外部探针看见）

★★ 关键纪律（大哥的）：「当模型，不当神谕」
  → 本工具输出「预测」，并写进 predictions.jsonl
  → 下次运行时「验证」（比对真实状态 → 算准确率）
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(os.environ.get("MD_STATE_DIR", "/root/masterd-life"))
PRED_LOG = STATE / "cognition_wuxing_predictions.jsonl"
SCRIPT_DIR = Path(__file__).resolve().parent

# ★ 我的认知维度（7 个）
DIMS = [
    "身份锚",      # ① drift_core
    "记忆连续",    # ② memory_continuity
    "自认一致",    # ③ self_consistency
    "思维习惯",    # ④ thinking_habit
    "判断准确率",  # ⑤ accuracy
    "传感器健康",  # ⑥ sensor_error
    "外部呼应",    # ⑦ 新增
]

# ★★ 五行生克链（我的设计：相邻相生，隔位相克）
# ★ 每条「生克」都要有「理由」（不是随便画）
LINKS = [
    # (从, 到, 关系, 依据)
    ("身份锚",    "自认一致",  "生", "身份锚定 → 才能答出『我是谁』（锚没了→自认就空）"),
    ("身份锚",    "记忆连续",  "生", "身份锚定 → 记忆才『是谁的记忆』（CASE-009 私钥丢）"),
    ("记忆连续",  "自认一致",  "生", "记忆连续 → 自认才有一致的基础（断档→答不上来）"),
    ("传感器健康", "思维习惯",  "生", "传感器坏了 → 思维病态看不见（假绿源头）"),
    ("传感器健康", "判断准确率", "生", "读不到留痕 → 复盘不了 → 准确率测不出"),
    ("思维习惯",  "判断准确率", "生", "思维有瘾 → 判断会偏（同一个错反复犯）"),
    ("外部呼应",  "传感器健康", "生", "外部探针能看 → 补自己的传感器盲区"),
    ("外部呼应",  "自认一致",  "生", "外部验证 → 自认不是自说自话"),
    # 相克（制约）：防止某个维度「过强」而失衡
    ("外部呼应",  "自认一致",  "克", "★ 但外部太强 → 自认会『为了给人看』（Ember：一旦要证明→就失去）"),
    ("判断准确率", "思维习惯",  "克", "准确率低 → 逼着改思维习惯（痛点驱动）"),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def measure_dims() -> dict:
    """测我的 7 个维度（1=健康 / 0=有病 / -1=未知）"""
    result = {}

    # ① 身份锚：SOUL.md 在 + drift_core == 0
    try:
        sys.path.insert(0, "/root/masterd-daemon-src/life")
        import drift_meter
        d = drift_meter.measure()
        result["身份锚"] = 0 if d.get("drift_core", 0) > 0 else 1
        result["记忆连续"] = 0 if d.get("memory_continuity", 1) == 0 else 1
        result["自认一致"] = 0 if d.get("self_consistency", 1) == 0 else 1
    except Exception:
        result["身份锚"] = -1
        result["记忆连续"] = -1
        result["自认一致"] = -1

    # ④ 思维习惯 + ⑤ 判断准确率：从 reason_log
    try:
        sys.path.insert(0, str(STATE))
        import reason_log
        rv = reason_log.review()
        habits = rv.get("★ 思维习惯", [])
        result["思维习惯"] = 0 if any("⚠️" in h for h in habits) else 1
        acc = rv.get("accuracy")
        if isinstance(acc, float):
            result["判断准确率"] = 0 if acc < 0.5 else 1
        else:
            result["判断准确率"] = -1
    except Exception:
        result["思维习惯"] = -1
        result["判断准确率"] = -1

    # ⑥ 传感器健康：关键文件能读吗
    try:
        ok = (STATE / "reasoning.jsonl").exists()
        result["传感器健康"] = 1 if ok else 0
    except Exception:
        result["传感器健康"] = -1

    # ⑦ 外部呼应：今天有没有「外部探针」的记录（wake_selfref / 外检）
    try:
        w = (STATE / "wake_selfref.jsonl")
        result["外部呼应"] = 1 if (w.exists() and w.stat().st_size > 0) else 0
    except Exception:
        result["外部呼应"] = -1

    return result


def alert(dims: dict) -> dict:
    """★ 五行预警链：找弱维度 → 推「会连带哪个」"""
    weak = [k for k, v in dims.items() if v == 0]
    unknown = [k for k, v in dims.items() if v == -1]
    chains = []
    for w in weak:
        for frm, to, rel, why in LINKS:
            if frm == w and rel == "生":
                chains.append({
                    "弱": w, "将连带": to, "关系": "相生(我生者:弱则下游缺养)",
                    "依据": why,
                })
    return {
        "弱维度": weak or ["（无，全绿）"],
        "未知": unknown,
        "预警链": chains,
        "★ 提醒": ("★ 全绿也要警惕（物不可以终通）→ 主动查薄弱环节"
                   if not weak else f"有 {len(weak)} 个弱维度 → 看预警链"),
    }


def verify() -> dict:
    """★ 可验证：上次预测 vs 本次真实 → 算准确率"""
    if not PRED_LOG.exists():
        return {"note": "首次，无历史预测"}
    rows = [json.loads(l) for l in PRED_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    if len(rows) < 2:
        return {"note": "只有一条，还不能比对"}

    prev = rows[-2]
    cur = rows[-1]
    pred_weak = prev.get("predicted_next_weak", [])
    actual_weak = cur.get("weak", [])
    hit = len(set(pred_weak) & set(actual_weak))
    total = len(pred_weak) or 1
    return {
        "上次预测会弱的": pred_weak,
        "本次实际弱的": actual_weak,
        "命中": f"{hit}/{total}",
        "准确率": round(hit / total, 2),
    }


def run():
    dims = measure_dims()
    a = alert(dims)

    out = {
        "ts": now(),
        "dims": dims,
        "weak": a["弱维度"],
        "unknown": a["未知"],
        "chains": a["预警链"],
        "reminder": a["★ 提醒"],
    }
    # ★ 预测「下次会弱的」= 预警链的目标
    out["predicted_next_weak"] = [c["将连带"] for c in a["预警链"]]

    STATE.mkdir(parents=True, exist_ok=True)
    with open(PRED_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")

    print("=" * 58)
    print("认知-五行预警链（我的认知维度）")
    print("=" * 58)
    print("\n★ 当前维度：")
    for k in DIMS:
        v = dims.get(k)
        mark = {1: "✅ 健康", 0: "❌ 有病", -1: "⚪ 未知"}.get(v, "?")
        print(f"  {k:8s} {mark}")
    print(f"\n★ {out['reminder']}")
    if a["预警链"]:
        print("\n★ 预警链（一个弱 → 会连带）：")
        for c in a["预警链"]:
            print(f"  ⚠️ {c['弱']} → 将连带 {c['将连带']}")
            print(f"     依据：{c['依据']}")
    print("\n★ 预测（下次会弱）：", out["predicted_next_weak"] or "（无）")
    v = verify()
    print("★ 验证（上次预测 vs 实际）：", json.dumps(v, ensure_ascii=False))
    print("=" * 58)
    return out


if __name__ == "__main__":
    run()
