"""Message source-of-truth store backed by SQLite + FTS5."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sqlite_connection import open_sqlite


@dataclass(frozen=True)
class InsertMessagesResult:
    inserted_count: int
    duplicate_count: int
    invalid_count: int
    fts_indexed_count: int
    fts_failed_count: int


class MessageStore:
    """Store normalized Telegram messages and maintain FTS5 state."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def insert_messages(self, items: list[dict[str, Any]]) -> InsertMessagesResult:
        inserted_ids: list[int] = []
        inserted_count = 0
        duplicate_count = 0
        invalid_count = 0

        with closing(open_sqlite(self.db_path)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for item in items:
                    try:
                        record = _normalize_message(item)
                    except ValueError:
                        invalid_count += 1
                        continue

                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO telegram_messages (
                            guid,
                            platform,
                            source_id,
                            source_name,
                            feed_id,
                            message_id,
                            url,
                            title,
                            summary,
                            raw_text_full,
                            search_text,
                            pub_at,
                            pub_str,
                            external_url,
                            external_urls_json,
                            preview_title,
                            media_json,
                            collected_at
                        )
                        VALUES (
                            :guid,
                            :platform,
                            :source_id,
                            :source_name,
                            :feed_id,
                            :message_id,
                            :url,
                            :title,
                            :summary,
                            :raw_text_full,
                            :search_text,
                            :pub_at,
                            :pub_str,
                            :external_url,
                            :external_urls_json,
                            :preview_title,
                            :media_json,
                            :collected_at
                        )
                        """,
                        record,
                    )
                    if cursor.rowcount == 1:
                        inserted_count += 1
                        inserted_ids.append(int(cursor.lastrowid))
                    else:
                        duplicate_count += 1
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        fts_indexed_count, fts_failed_count = self.index_messages_fts(inserted_ids)
        return InsertMessagesResult(
            inserted_count=inserted_count,
            duplicate_count=duplicate_count,
            invalid_count=invalid_count,
            fts_indexed_count=fts_indexed_count,
            fts_failed_count=fts_failed_count,
        )

    def index_pending_fts(self, batch_size: int = 1000) -> tuple[int, int]:
        with closing(open_sqlite(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM telegram_messages
                WHERE fts_indexed = 0
                AND fts_error_count < 5
                ORDER BY collected_at ASC, id ASC
                LIMIT ?
                """,
                (batch_size,),
            ).fetchall()
        ids = [int(row["id"]) for row in rows]
        return self.index_messages_fts(ids)

    def index_messages_fts(self, message_ids: list[int]) -> tuple[int, int]:
        indexed = 0
        failed = 0
        for message_id in message_ids:
            try:
                self._index_one_fts(message_id)
                indexed += 1
            except sqlite3.DatabaseError as exc:
                self._mark_fts_error(message_id, str(exc))
                failed += 1
        return indexed, failed

    def get_by_guid(self, guid: str) -> dict[str, Any] | None:
        with closing(open_sqlite(self.db_path, readonly=True)) as conn:
            row = conn.execute(
                "SELECT * FROM telegram_messages WHERE guid = ?",
                (guid,),
            ).fetchone()
        return dict(row) if row else None

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), 100)
        with closing(open_sqlite(self.db_path, readonly=True)) as conn:
            rows = conn.execute(
                """
                SELECT
                    m.*,
                    bm25(telegram_messages_fts, 5.0, 2.0, 1.0, 0.5) AS rank
                FROM telegram_messages_fts
                JOIN telegram_messages m ON m.id = telegram_messages_fts.rowid
                WHERE telegram_messages_fts MATCH ?
                ORDER BY rank ASC, m.pub_at DESC, m.id DESC
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _index_one_fts(self, message_id: int) -> None:
        with closing(open_sqlite(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT id, title, summary, raw_text_full, source_name
                FROM telegram_messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO telegram_messages_fts (
                        rowid,
                        title,
                        summary,
                        raw_text_full,
                        source_name
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["title"],
                        row["summary"],
                        row["raw_text_full"],
                        row["source_name"],
                    ),
                )
                conn.execute(
                    """
                    UPDATE telegram_messages
                    SET fts_indexed = 1,
                        fts_indexed_at = CURRENT_TIMESTAMP,
                        fts_last_error = NULL
                    WHERE id = ?
                    """,
                    (message_id,),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _mark_fts_error(self, message_id: int, error_message: str) -> None:
        with closing(open_sqlite(self.db_path)) as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE telegram_messages
                    SET fts_indexed = 0,
                        fts_error_count = fts_error_count + 1,
                        fts_last_error = ?
                    WHERE id = ?
                    """,
                    (error_message, message_id),
                )


def _normalize_message(item: dict[str, Any]) -> dict[str, Any]:
    platform = str(item.get("platform") or "telegram").strip()
    source_id = _required(item, "source_id")
    message_id = _required(item, "message_id")
    source_name = str(item.get("source_name") or source_id).strip()
    title = str(item.get("title") or "Untitled Telegram message").strip()
    summary = str(item.get("summary") or "").strip()
    raw_text_full = str(item.get("raw_text_full") or summary).strip()
    url = _required(item, "url")
    collected_at = str(item.get("collected_at") or _utc_now()).strip()
    external_urls = _external_urls(item)
    external_url = str(item.get("external_url") or (external_urls[0] if external_urls else "")).strip()

    return {
        "guid": f"{platform}:{source_id}:{message_id}",
        "platform": platform,
        "source_id": source_id,
        "source_name": source_name,
        "feed_id": str(item.get("feed_id") or "").strip() or None,
        "message_id": message_id,
        "url": url,
        "title": title,
        "summary": summary,
        "raw_text_full": raw_text_full,
        "search_text": _search_text(title, summary, raw_text_full, source_name),
        "pub_at": str(item.get("pub_str") or item.get("pub_at") or "").strip() or None,
        "pub_str": str(item.get("pub_str") or "").strip() or None,
        "external_url": external_url or None,
        "external_urls_json": json.dumps(external_urls, ensure_ascii=False),
        "preview_title": str(item.get("preview_title") or "").strip() or None,
        "media_json": _json_or_none(item.get("media_json")),
        "collected_at": collected_at,
    }


def _external_urls(item: dict[str, Any]) -> list[str]:
    raw_urls = item.get("external_urls")
    if isinstance(raw_urls, list):
        urls = [str(url).strip() for url in raw_urls if str(url).strip()]
    else:
        url = str(item.get("external_url") or "").strip()
        urls = [url] if url else []

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)
    return unique_urls


def _search_text(*parts: str) -> str:
    return "\n".join(part.strip().lower() for part in parts if part.strip())


def _json_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _required(item: dict[str, Any], key: str) -> str:
    value = str(item.get(key, "")).strip()
    if not value:
        raise ValueError(f"message missing required field: {key}")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
