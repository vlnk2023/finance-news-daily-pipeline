"""Durable ingest spool backed by a dedicated SQLite database."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .sqlite_connection import open_sqlite


OPEN_STATUSES = ("pending", "retrying")


class SpoolStore:
    """Reliable input queue for parsed items."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def append_item(self, item: dict[str, Any]) -> int:
        guid = _canonical_guid(item)
        source_id = _required(item, "source_id")
        message_id = _required(item, "message_id")
        payload_json = json.dumps(item, ensure_ascii=False, sort_keys=True)

        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ingest_spool (
                        guid,
                        source_id,
                        message_id,
                        payload_json,
                        status
                    )
                    VALUES (?, ?, ?, ?, 'pending')
                    """,
                    (guid, source_id, message_id, payload_json),
                )
                row = conn.execute(
                    """
                    SELECT id
                    FROM ingest_spool
                    WHERE guid = ?
                    AND status IN ('pending', 'retrying')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (guid,),
                ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to append or find open spool item: {guid}")
            return int(row["id"])

    def get_pending_batch(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(open_sqlite(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT id, guid, source_id, message_id, payload_json, status, retry_count
                FROM ingest_spool
                WHERE status IN ('pending', 'retrying')
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_spool_item(row) for row in rows]

    def ack(self, spool_id: int) -> None:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ingest_spool
                    SET status = 'acked',
                        acked_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        error_message = NULL
                    WHERE id = ?
                    """,
                    (spool_id,),
                )

    def mark_retrying(self, spool_id: int, error_message: str) -> None:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ingest_spool
                    SET status = 'retrying',
                        retry_count = retry_count + 1,
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (error_message, spool_id),
                )

    def mark_failed(self, spool_id: int, error_message: str) -> None:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE ingest_spool
                    SET status = 'failed',
                        error_message = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (error_message, spool_id),
                )

    def expire_old_pending(self, max_age_hours: int = 72) -> int:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE ingest_spool
                    SET status = 'expired',
                        updated_at = CURRENT_TIMESTAMP,
                        error_message = 'pending item expired'
                    WHERE status IN ('pending', 'retrying')
                    AND created_at < datetime('now', ?)
                    """,
                    (f"-{max_age_hours} hours",),
                )
            return int(cursor.rowcount)

    def purge_acked(self, retention_hours: int = 48) -> int:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    DELETE FROM ingest_spool
                    WHERE status = 'acked'
                    AND acked_at < datetime('now', ?)
                    """,
                    (f"-{retention_hours} hours",),
                )
            return int(cursor.rowcount)

    def count_by_status(self) -> dict[str, int]:
        with closing(open_sqlite(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM ingest_spool
                GROUP BY status
                """
            ).fetchall()
        return {row["status"]: int(row["count"]) for row in rows}


def _row_to_spool_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "guid": row["guid"],
        "source_id": row["source_id"],
        "message_id": row["message_id"],
        "payload": json.loads(row["payload_json"]),
        "status": row["status"],
        "retry_count": int(row["retry_count"]),
    }


def _required(item: dict[str, Any], key: str) -> str:
    value = str(item.get(key, "")).strip()
    if not value:
        raise ValueError(f"spool item missing required field: {key}")
    return value


def _canonical_guid(item: dict[str, Any]) -> str:
    platform = str(item.get("platform") or "telegram").strip()
    source_id = _required(item, "source_id")
    message_id = _required(item, "message_id")
    return f"{platform}:{source_id}:{message_id}"
