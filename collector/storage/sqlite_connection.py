"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def open_sqlite(path: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    db_path = Path(path)
    if readonly:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=3000")
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")

    conn.row_factory = sqlite3.Row
    return conn


def check_fts5_available(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.fts5_check USING fts5(x)")
        conn.execute("DROP TABLE temp.fts5_check")
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("SQLite FTS5 extension is not available") from exc

