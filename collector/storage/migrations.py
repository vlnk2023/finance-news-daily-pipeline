"""Small SQL migration runner for SQLite databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .sqlite_connection import check_fts5_available, open_sqlite


def migrate_database(
    db_path: str | Path,
    migrations_dir: str | Path,
    *,
    require_fts5: bool = False,
) -> list[str]:
    conn = open_sqlite(db_path)
    try:
        if require_fts5:
            check_fts5_available(conn)
        _ensure_schema_migrations(conn)
        applied = _applied_versions(conn)
        newly_applied: list[str] = []

        for migration_path in sorted(Path(migrations_dir).glob("*.sql")):
            version = migration_path.stem
            if version in applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            escaped_version = version.replace("'", "''")
            try:
                conn.executescript(
                    f"""
                    BEGIN;
                    {sql}
                    INSERT INTO schema_migrations(version) VALUES ('{escaped_version}');
                    COMMIT;
                    """
                )
            except sqlite3.DatabaseError:
                conn.rollback()
                raise
            newly_applied.append(version)

        return newly_applied
    finally:
        conn.close()


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}
