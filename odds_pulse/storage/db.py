"""SQLite 数据落地：把每次采集的市场快照存下来，供"追踪概率变化"使用。

关键点：
  - 表 market_snapshots 以 (source, market_id, captured_at) 为主键，避免重复插入。
  - 所有 SQL 使用参数化查询（? 占位符），不使用字符串拼接，防注入也保证类型正确。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..data.models import Market

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_snapshots (
    source       TEXT    NOT NULL,
    market_id    TEXT    NOT NULL,
    question     TEXT    NOT NULL,
    probability  REAL    NOT NULL,
    volume       REAL    NOT NULL DEFAULT 0,
    captured_at  TEXT    NOT NULL,
    notes        TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (source, market_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_lookup
    ON market_snapshots (source, market_id, captured_at);
"""


class MarketStore:
    """封装对 market_snapshots 表的读写。"""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)

    def init_db(self) -> None:
        """建表（幂等，可反复调用）。"""
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save_markets(self, markets: list[Market]) -> int:
        """批量插入快照，返回实际写入条数。重复主键会更新（INSERT OR REPLACE）。"""
        if not markets:
            return 0
        rows = [
            (
                m.source, m.market_id, m.question,
                m.probability, m.volume,
                m.captured_at.isoformat(), m.notes,
            )
            for m in markets
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO market_snapshots "
                "(source, market_id, question, probability, volume, captured_at, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_history(self, source: str, market_id: str, limit: int = 50) -> list[Market]:
        """取某市场最近 limit 条历史快照（按时间升序）。"""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM market_snapshots "
                "WHERE source=? AND market_id=? "
                "ORDER BY captured_at DESC LIMIT ?",
                (source, market_id, limit),
            ).fetchall()
        # 转回 Market 模型，保持与上游一致的抽象
        return [
            Market(
                source=r["source"], market_id=r["market_id"], question=r["question"],
                probability=r["probability"], volume=r["volume"],
                captured_at=r["captured_at"], notes=r["notes"],
            )
            for r in reversed(rows)
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
