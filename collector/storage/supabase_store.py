"""Supabase storage adapter for collected news items."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from collector.runner import FeedCollectionResult


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase environment variables are missing."""


@dataclass(frozen=True)
class SupabaseWriteStats:
    sources_upserted: int
    items_upserted: int


class SupabaseStore:
    """Write collector results to Supabase through the PostgREST API."""

    def __init__(
        self,
        *,
        url: str | None = None,
        service_role_key: str | None = None,
        timeout_seconds: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.service_role_key = (
            service_role_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
            or ""
        )
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        if not self.url or not self.service_role_key:
            raise SupabaseConfigError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set to write Supabase."
            )

    def upsert_results(
        self,
        results: list[FeedCollectionResult],
        *,
        feeds_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> SupabaseWriteStats:
        feeds_by_id = feeds_by_id or {}
        source_rows = []
        item_rows = []

        for result in results:
            feed = feeds_by_id.get(result.feed_id, {})
            source_rows.append(_source_row(result, feed))
            item_rows.extend(_item_row(item) for item in result.items)

        sources_upserted = self._upsert("sources", source_rows, on_conflict="id")
        items_upserted = self._upsert("news_items", item_rows, on_conflict="guid")
        return SupabaseWriteStats(
            sources_upserted=sources_upserted,
            items_upserted=items_upserted,
        )

    def _upsert(self, table: str, rows: list[dict[str, Any]], *, on_conflict: str) -> int:
        if not rows:
            return 0

        endpoint = f"{self.url}/rest/v1/{table}"
        response = self.session.post(
            endpoint,
            params={"on_conflict": on_conflict},
            headers={
                "apikey": self.service_role_key,
                "authorization": f"Bearer {self.service_role_key}",
                "content-type": "application/json",
                "prefer": "resolution=merge-duplicates,return=minimal",
            },
            data=json.dumps(rows, ensure_ascii=False),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return len(rows)

    def fetch_pending_translation_items(self, *, limit: int = 200) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/news_items"
        response = self.session.get(
            endpoint,
            params={
                "select": "id,guid,title,summary,source_lang,translation_status",
                "translation_status": "eq.pending",
                "source_lang": "is.null",
                "order": "published_at.desc.nullslast",
                "limit": str(limit),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def update_news_item(self, item_id: str, fields: dict[str, Any]) -> None:
        endpoint = f"{self.url}/rest/v1/news_items"
        payload = {**fields, "updated_at": _now_iso()}
        response = self.session.patch(
            endpoint,
            params={"id": f"eq.{item_id}"},
            headers={
                **self._headers(),
                "content-type": "application/json",
                "prefer": "return=minimal",
            },
            data=json.dumps(payload, ensure_ascii=False),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
        }


def _source_row(result: FeedCollectionResult, feed: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.source_id,
        "name": feed.get("source_name") or result.source_id,
        "platform": feed.get("platform") or "telegram",
        "url": result.url,
        "language_hint": feed.get("language_hint"),
        "enabled": bool(feed.get("enabled", True)),
        "collect_config": feed.get("collect") or {},
        "updated_at": _now_iso(),
    }


def _item_row(item: dict[str, Any]) -> dict[str, Any]:
    published_at = _normalize_timestamp(item.get("pub_str"))
    raw_text = item.get("raw_text_full") or item.get("summary") or ""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    guid = item.get("guid") or _content_hash(title, summary, item.get("url") or "")

    return {
        "source_id": item.get("source_id") or item.get("feed_id") or "",
        "feed_id": item.get("feed_id") or "",
        "guid": guid,
        "content_hash": _content_hash(title, raw_text, item.get("url") or ""),
        "message_id": item.get("message_id") or "",
        "title": title,
        "summary": summary,
        "source_lang": item.get("source_lang"),
        "title_zh": item.get("title_zh"),
        "summary_zh": item.get("summary_zh"),
        "url": item.get("url") or "",
        "external_url": item.get("external_url") or "",
        "external_urls": item.get("external_urls") or [],
        "preview_title": item.get("preview_title") or "",
        "published_at": published_at,
        "collected_at": _normalize_timestamp(item.get("collected_at")) or _now_iso(),
        "translation_status": item.get("translation_status") or "pending",
        "raw_json": item,
        "updated_at": _now_iso(),
    }


def _content_hash(*parts: str) -> str:
    canonical = "\n".join(part.strip() for part in parts if part)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_timestamp(value: Any) -> str | None:
    if not value:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
