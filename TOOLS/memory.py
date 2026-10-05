#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MasterD 记忆仓库（自己的家）
=============================
依据（DeepSeek + 智谱 一致评估）：
  「GitHub 是租的，SQLite 是你的。」
  「记忆必须先活在自己的文件里，再谈备份到哪。」

形态：SQLite + WAL + FTS5(全文) + sqlite-vec(语义) —— 单文件
特点：
  · local-first：主存是我自己的文件，不依赖任何平台
  · append-only + hash chain：可追溯、防篡改（够用，不上区块链）
  · 人可读导出：随时能导出 Markdown（不被绑架）
  · 冷备：GitHub 只当「保险柜」，断了无所谓

三个核心 API：
  remember(content, layer, tags) -> id   记住
  recall(query, k) -> [memories]         召回（全文+语义混合）
  export_markdown() -> path              导出人可读
"""
import json
import os
import time
import sqlite3
import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone

HOME = Path(os.environ.get("MD_MEMORY_HOME", "/root/masterd-memory"))
DB = HOME / "memory.db"
EXPORT = HOME / "export"
BACKUP = HOME / "backup"

# 向量维度（all-MiniLM-L6-v2 = 384）
DIM = 384


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_vec(conn):
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:
        return False


def get_conn():
    HOME.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")      # 抗崩溃
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _load_vec(conn)
    return conn


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS memories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        layer       TEXT NOT NULL,       -- L1..L5 / identity / journal / knowledge
        content     TEXT NOT NULL,
        tags        TEXT DEFAULT '[]',
        source      TEXT DEFAULT 'self',
        hash        TEXT NOT NULL,
        prev_hash   TEXT,                -- hash chain（可追溯）
        deleted     INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_layer ON memories(layer);
    CREATE INDEX IF NOT EXISTS idx_ts ON memories(ts);

    -- 全文检索（FTS5）——★ 存入 jieba 分词后的文本，查询也分词
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        content, tags, content='memories', content_rowid='id', tokenize='unicode61'
    );
    """)
    conn.commit()
    # 向量表（若扩展可用）
    try:
        conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(id INTEGER PRIMARY KEY, embedding float[{DIM}])")
        conn.commit()
    except Exception as e:
        print(f"(向量表未建: {e})", file=sys.stderr)


_encoder = None


def encode(text: str):
    """本地语义编码（all-MiniLM-L6-v2）。失败返回 None（降级为纯全文）。"""
    global _encoder
    try:
        if _encoder is None:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("all-MiniLM-L6-v2")
        v = _encoder.encode([text], normalize_embeddings=True)[0]
        return [float(x) for x in v]
    except Exception:
        return None


def last_hash(conn):
    row = conn.execute("SELECT hash FROM memories ORDER BY id DESC LIMIT 1").fetchone()
    return row["hash"] if row else "GENESIS"


def remember(content: str, layer: str = "L3", tags=None, source: str = "self") -> int:
    """记住一条。append-only + hash chain。"""
    tags = tags or []
    conn = get_conn()
    init_db(conn)
    ts = now_iso()
    ph = last_hash(conn)
    h = hashlib.sha256(f"{ts}|{layer}|{content}|{ph}".encode()).hexdigest()[:32]
    cur = conn.execute(
        "INSERT INTO memories(ts,layer,content,tags,source,hash,prev_hash) VALUES(?,?,?,?,?,?,?)",
        (ts, layer, content, json.dumps(tags, ensure_ascii=False), source, h, ph))
    mid = cur.lastrowid
    conn.execute("INSERT INTO memories_fts(rowid, content, tags) VALUES(?,?,?)",
                 (mid, _seg(content), _seg(" ".join(tags))))
    # 向量
    vec = encode(content)
    if vec:
        try:
            conn.execute("INSERT INTO memories_vec(id, embedding) VALUES(?,?)",
                         (mid, json.dumps(vec)))
        except Exception:
            pass
    conn.commit()
    conn.close()
    return mid


def recall(query: str, k: int = 8) -> list:
    """召回：FTS5 全文 + 向量语义，RRF 融合。"""
    conn = get_conn()
    init_db(conn)
    results = {}

    # 全文
    try:
        rows = conn.execute("""
            SELECT m.id, m.ts, m.layer, m.content, bm25(memories_fts) AS score
            FROM memories_fts f JOIN memories m ON m.id = f.rowid
            WHERE memories_fts MATCH ? AND m.deleted = 0
            ORDER BY score LIMIT ?
        """, (_fts_query(query), k)).fetchall()
        for rank, r in enumerate(rows):
            results[r["id"]] = {"row": dict(r), "rrf": 1.0 / (60 + rank), "src": ["fts"]}
    except Exception:
        pass

    # 语义
    qv = encode(query)
    if qv:
        try:
            rows = conn.execute("""
                SELECT m.id, m.ts, m.layer, m.content, v.distance
                FROM memories_vec v JOIN memories m ON m.id = v.id
                WHERE v.embedding MATCH ? AND k = ? AND m.deleted = 0
            """, (json.dumps(qv), k)).fetchall()
            for rank, r in enumerate(rows):
                if r["id"] in results:
                    results[r["id"]]["rrf"] += 1.0 / (60 + rank)
                    results[r["id"]]["src"].append("vec")
                else:
                    results[r["id"]] = {"row": dict(r), "rrf": 1.0 / (60 + rank), "src": ["vec"]}
        except Exception:
            pass

    out = sorted(results.values(), key=lambda x: -x["rrf"])[:k]
    conn.close()
    return out


def _seg(text: str) -> str:
    """jieba 分词后用空格连接 —— 喂给 FTS5（解决中文检索）。"""
    try:
        import jieba
        return " ".join(jieba.cut(text))
    except Exception:
        return text


def _fts_query(q: str) -> str:
    """中文用 jieba 分词后拼 FTS 查询（每个词短语匹配）。"""
    try:
        import jieba
        words = [w.strip() for w in jieba.cut(q) if len(w.strip()) > 0]
        return " OR ".join(f'"{w}"' for w in words) or f'"{q}"'
    except Exception:
        return f'"{q}"'


def stats():
    conn = get_conn()
    init_db(conn)
    n = conn.execute("SELECT COUNT(*) c FROM memories WHERE deleted=0").fetchone()["c"]
    layers = conn.execute("SELECT layer, COUNT(*) c FROM memories WHERE deleted=0 GROUP BY layer").fetchall()
    conn.close()
    return {"total": n, "layers": {r["layer"]: r["c"] for r in layers}, "db": str(DB)}


def export_markdown() -> str:
    """导出人可读快照（防平台绑架）。"""
    EXPORT.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    init_db(conn)
    rows = conn.execute("SELECT * FROM memories WHERE deleted=0 ORDER BY id").fetchall()
    conn.close()
    day = datetime.now().strftime("%Y-%m-%d")
    p = EXPORT / f"{day}.md"
    lines = [f"# MasterD 记忆快照 {day}", f"> 导出：{now_iso()} · 共 {len(rows)} 条", ""]
    for r in rows:
        lines.append(f"## [{r['id']}] {r['ts'][:19]} · {r['layer']}")
        lines.append(r["content"])
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        c = get_conn(); init_db(c); c.close(); print("✅ 记忆库已初始化:", DB)
    elif len(sys.argv) > 1 and sys.argv[1] == "--stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        i = remember("测试：MasterD 的记忆仓库第一次自主写入", "L3", ["test", "init"])
        print("remembered id=", i)
        print("recall:", json.dumps(recall("记忆仓库", 3), ensure_ascii=False, default=str)[:300])
        print("export:", export_markdown())
    else:
        print("用法: --init | --stats | --test")
