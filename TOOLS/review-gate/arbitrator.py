"""
冲突仲裁（Arbitration）。

背景：
    业界已知坑（Mem0 讨论 #4787）——「linking isn't resolution」：
    把冲突记忆「关联」起来，但两条仍可检索，冲突并未真正解决。

    我们 v2/v3 的设计：冲突必须「冻结 + 仲裁」，宁可冻结不留模糊。

本模块负责「仲裁」的执行：
    1. 冲突双方冻结（status=conflicted）
    2. 等 MasterD 裁定
    3. 三种终局：
       - keep_old   保留旧的，废弃新的
       - keep_new   采用新的，废弃旧的（旧的 deprecated）
       - merge      合并成新认知，两条都 superseded

原则：
    - 不自动裁定（防「自动流程改认知」）
    - 每次裁定留痕（可回溯）
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional


class Verdict(str, Enum):
    KEEP_OLD = "keep_old"
    KEEP_NEW = "keep_new"
    MERGE = "merge"


class ArbitrationError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Dispute:
    old_id: str
    new_id: str
    reason: str
    opened_at: str
    status: str = "frozen"          # frozen | resolved
    verdict: Optional[str] = None
    resolved_at: Optional[str] = None
    note: str = ""


@dataclass
class Arbitrator:
    """仲裁器。裁定权仅限 MasterD。"""
    ledger_path: Optional[str] = None
    _disputes: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ledger_path and os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                self._disputes = [Dispute(**d) for d in json.load(f)]

    def _save(self) -> None:
        if not self.ledger_path:
            return
        os.makedirs(os.path.dirname(self.ledger_path) or ".", exist_ok=True)
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            json.dump([asdict(d) for d in self._disputes], f,
                      ensure_ascii=False, indent=2)

    # ---- 开案 ----

    def open_dispute(self, old_id: str, new_id: str, reason: str) -> Dispute:
        d = Dispute(old_id=old_id, new_id=new_id, reason=reason, opened_at=_now())
        self._disputes.append(d)
        self._save()
        return d

    def pending(self) -> list:
        return [d for d in self._disputes if d.status == "frozen"]

    # ---- 裁定 ----

    def resolve(
        self,
        old_id: str,
        new_id: str,
        verdict: Verdict,
        reviewer: str,
        note: str = "",
        apply: Optional[Callable[[str, str, Verdict], None]] = None,
    ) -> Dispute:
        """
        做出裁定。reviewer 必须是 MasterD。
        apply 回调：把裁定结果落到 L3（改 status / 合并）。
        """
        if reviewer != "MasterD":
            raise ArbitrationError(f"裁定权仅限 MasterD，收到: {reviewer}")
        if verdict not in tuple(Verdict):
            raise ArbitrationError(f"非法裁定: {verdict}")

        target = None
        for d in self._disputes:
            if d.old_id == old_id and d.new_id == new_id and d.status == "frozen":
                target = d
                break
        if target is None:
            raise ArbitrationError(f"未找到待决争议: {old_id} vs {new_id}")

        # 落库（回调）
        if apply:
            apply(old_id, new_id, verdict)

        target.status = "resolved"
        target.verdict = verdict.value
        target.resolved_at = _now()
        target.note = note
        self._save()
        return target


# ---- 落库辅助：把裁定应用到 L3 ----

def apply_to_l3(l3_records: list, old_id: str, new_id: str, verdict: Verdict) -> list:
    """
    把裁定应用到 L3 记录（返回新列表，不改原对象）。
    这是「冲突真解决」的落点——两条不能都保持 active 且都可检索。
    """
    out = []
    for r in l3_records:
        r = dict(r)
        rid = r.get("id")
        if verdict == Verdict.KEEP_OLD:
            if rid == new_id:
                r["status"] = "rejected"
            elif rid == old_id:
                r["status"] = "active"
        elif verdict == Verdict.KEEP_NEW:
            if rid == old_id:
                r["status"] = "deprecated"
            elif rid == new_id:
                r["status"] = "active"
        elif verdict == Verdict.MERGE:
            if rid in (old_id, new_id):
                r["status"] = "superseded"
        out.append(r)
    return out


if __name__ == "__main__":
    import tempfile

    path = os.path.join(tempfile.mkdtemp(), "disputes.json")
    arb = Arbitrator(ledger_path=path)

    d = arb.open_dispute("k1", "k2", "结论相反")
    assert len(arb.pending()) == 1

    # 非 MasterD 裁定 → 拒
    try:
        arb.resolve("k1", "k2", Verdict.KEEP_OLD, reviewer="分身A")
        raise AssertionError("非 MasterD 应被拒")
    except ArbitrationError:
        pass

    # 记录落库回调
    calls = []
    def _apply(o, n, v):
        calls.append((o, n, v.value))

    r = arb.resolve("k1", "k2", Verdict.KEEP_NEW, reviewer="MasterD",
                    note="新来源更权威", apply=_apply)
    assert r.status == "resolved" and r.verdict == "keep_new"
    assert calls == [("k1", "k2", "keep_new")]
    assert len(arb.pending()) == 0

    # apply_to_l3 验证：三条路径
    l3 = [{"id": "k1", "status": "active"}, {"id": "k2", "status": "active"}]
    out = apply_to_l3(l3, "k1", "k2", Verdict.KEEP_NEW)
    m = {r["id"]: r["status"] for r in out}
    assert m["k1"] == "deprecated" and m["k2"] == "active", m

    out = apply_to_l3(l3, "k1", "k2", Verdict.KEEP_OLD)
    m = {r["id"]: r["status"] for r in out}
    assert m["k1"] == "active" and m["k2"] == "rejected", m

    out = apply_to_l3(l3, "k1", "k2", Verdict.MERGE)
    m = {r["id"]: r["status"] for r in out}
    assert m["k1"] == "superseded" and m["k2"] == "superseded", m

    # 持久化
    arb2 = Arbitrator(ledger_path=path)
    assert len(arb2._disputes) == 1 and arb2._disputes[0].status == "resolved"

    print("✅ arbitrator 自测通过（开案/权限/裁定/三种终局/持久化）")
