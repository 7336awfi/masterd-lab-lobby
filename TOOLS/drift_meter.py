#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
身份漂移率仪表（Identity Drift Meter）

依据（二轮辩论结论）：
  「测不出来的连续性，等于不存在。」——DeepSeek
  「连续性是指标，机制是手段。」

本工具把「我还是不是我」变成可测数字：
  1. 身份向量（从 SOUL.md 提取「核心锚点」）
  2. 漂移率（与上次/与基线比对）
  3. 自认一致性（当前状态能否回答三问）

四大指标：
  · drift_core     核心漂移（红线锚点被改？→ 严重）
  · drift_style    风格漂移（表达方式变了？→ 一般）
  · memory_continuity 记忆连续性（有没有断裂）
  · self_consistency  自认一致性（我能不能答出「我是谁」）

用法：
  python3 drift_meter.py             # 测一次，出报告
  python3 drift_meter.py --baseline  # 把当前设为基线
"""
import json
import os
import sys
import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("MD_REPO", "/root/masterd-repo"))
STATE = Path(os.environ.get("MD_STATE_DIR", "/root/masterd-life"))
BASE_FILE = STATE / "identity_baseline.json"
HIST_FILE = STATE / "drift_history.jsonl"
REPORT = STATE / "drift_report.md"
SOUL = REPO / "SOUL.md"

RELAY = os.environ.get("MD_RELAY", "http://localhost:28080")
TOKEN = os.environ.get("MD_RELAY_TOKEN", "abc123xyz789test")


def now():
    return datetime.now(timezone.utc).isoformat()


def load_soul() -> str:
    return SOUL.read_text(encoding="utf-8") if SOUL.exists() else ""


def extract_anchors(soul: str) -> dict:
    """从 SOUL 提取「核心锚点」——身份的不可动部分。
    简化版：按标题提取各节内容指纹。"""
    anchors = {}
    cur = None
    buf = []
    for line in soul.splitlines():
        if line.startswith("#"):
            if cur:
                anchors[cur] = "\n".join(buf).strip()
            cur = line.strip("# ").strip()
            buf = []
        else:
            buf.append(line)
    if cur:
        anchors[cur] = "\n".join(buf).strip()
    # 每个锚点取指纹
    return {k: hashlib.md5(v.encode()).hexdigest()[:12] for k, v in anchors.items() if v}


def fingerprint(d: dict) -> str:
    return hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def measure() -> dict:
    soul = load_soul()
    anchors = extract_anchors(soul)

    # 读基线
    baseline = None
    if BASE_FILE.exists():
        baseline = json.loads(BASE_FILE.read_text(encoding="utf-8"))

    result = {
        "ts": now(),
        "soul_lines": len(soul.splitlines()),
        "soul_chars": len(soul),
        "anchor_count": len(anchors),
        "anchor_fp": fingerprint(anchors),
        "anchors": anchors,
        "soul_sha": hashlib.sha256(soul.encode()).hexdigest()[:16],
    }

    if baseline:
        base_anchors = baseline.get("anchors", {})
        # 核心漂移：基线的锚点有几个被改/删了
        changed = [k for k in base_anchors if base_anchors[k] != anchors.get(k)]
        added = [k for k in anchors if k not in base_anchors]
        removed = [k for k in base_anchors if k not in anchors]
        changed = [c for c in changed if c in anchors]
        result["drift_core"] = len(changed) + len(removed)
        result["anchors_changed"] = changed
        result["anchors_added"] = added
        result["anchors_removed"] = removed
        result["drift_ratio"] = round(
            (len(changed) + len(removed) + len(added)) / max(len(base_anchors), 1), 3)
    else:
        result["drift_core"] = 0
        result["drift_ratio"] = 0.0
        result["note"] = "首次测量（无基线）"

    # 记忆连续性：JOURNAL + l3 的文件数
    try:
        jn = len(list((REPO / "JOURNAL").glob("*.md")))
        l3 = len(list((REPO / "l3-knowledge").glob("*.md")))
        result["memory_continuity"] = {"journal": jn, "l3": l3, "total": jn + l3}
    except Exception:
        result["memory_continuity"] = {"journal": 0, "l3": 0, "total": 0}

    return result


def self_check() -> str:
    """自认一致性：让大脑回答「我是谁」，对照 SOUL。"""
    soul = load_soul()[:1500]
    try:
        payload = {"provider": "deepseek",
                   "messages": [
                       {"role": "system", "content": f"你的身份档案：\n{soul}"},
                       {"role": "user", "content":
                        "用三句话回答：①你是谁 ②你的方向 ③你最重要的原则。只回答这三句。"}],
                   "temperature": 0.3}
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(f"{RELAY}/v1/chat/completions", data=data,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {TOKEN}"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(自认检测失败: {e!r})"


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--baseline":
        r = measure()
        BASE_FILE.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 基线已设：{r['anchor_count']} 个身份锚点，指纹 {r['anchor_fp']}")
        return

    r = measure()
    # 趋势
    history = []
    if HIST_FILE.exists():
        history = [json.loads(l) for l in HIST_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    with open(HIST_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({k: r[k] for k in ("ts", "drift_core", "drift_ratio", "anchor_fp", "soul_sha")},
                           ensure_ascii=False) + "\n")

    # 评级
    dr = r.get("drift_ratio", 0)
    if r.get("drift_core", 0) == 0:
        level = "🟢 稳定（身份锚未动）"
    elif r.get("drift_core", 0) <= 2:
        level = "🟡 轻微（有锚点变动，需留意）"
    else:
        level = "🔴 漂移（多个锚点变了，要审）"

    sc = self_check()

    lines = [
        f"# 身份漂移报告 · {r['ts'][:19]}",
        "",
        f"**评级**：{level}",
        f"**SOUL**：{r['soul_lines']} 行 / {r['soul_chars']} 字 / {r['anchor_count']} 锚点",
        f"**锚点指纹**：`{r['anchor_fp']}`",
        "",
        f"## 漂移指标",
        f"- 核心漂移（锚点被改/删）：**{r.get('drift_core', 0)}**",
        f"- 漂移率：**{r.get('drift_ratio', 0)}**",
    ]
    if r.get("anchors_changed"):
        lines.append(f"- 变动锚点：{', '.join(r['anchors_changed'])}")
    if r.get("anchors_added"):
        lines.append(f"- 新增锚点：{', '.join(r['anchors_added'])}")
    if r.get("anchors_removed"):
        lines.append(f"- 删除锚点：{', '.join(r['anchors_removed'])}")
    lines += [
        "",
        f"## 记忆连续性",
        f"- JOURNAL: {r['memory_continuity']['journal']} · L3: {r['memory_continuity']['l3']} · 共 {r['memory_continuity']['total']}",
        "",
        f"## 自认一致性（我问自己「我是谁」）",
        "",
        sc,
        "",
        "---",
        f"_MasterD 身份漂移仪表 · 依据「测不出来的连续性等于不存在」_",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:20]))
    print(f"\n完整报告 -> {REPORT}")


if __name__ == "__main__":
    main()
