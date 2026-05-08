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

        existing_guids = self._fetch_existing_guids(
            [row["guid"] for row in item_rows if row.get("guid")]
        )

        new_item_rows = []
        existing_item_rows = []
        for row in item_rows:
            guid = row.get("guid", "")
            if guid and guid in existing_guids:
                existing_status = existing_guids[guid]
                row_copy = dict(row)
                if existing_status in ("translated", "failed"):
                    row_copy["translation_status"] = existing_status
                existing_item_rows.append(row_copy)
            else:
                new_item_rows.append(row)

        items_new = self._upsert("news_items", new_item_rows, on_conflict="guid") if new_item_rows else 0
        items_existing = self._upsert("news_items", existing_item_rows, on_conflict="guid") if existing_item_rows else 0

        return SupabaseWriteStats(
            sources_upserted=sources_upserted,
            items_upserted=items_new + items_existing,
        )

    def _fetch_existing_guids(self, guids: list[str]) -> dict[str, str]:
        if not guids:
            return {}

        batch_size = 100
        result = {}
        for i in range(0, len(guids), batch_size):
            batch = guids[i:i + batch_size]
            filter_value = ",".join(f'"{g}"' for g in batch)
            endpoint = f"{self.url}/rest/v1/news_items"
            response = self.session.get(
                endpoint,
                params={
                    "select": "guid,translation_status",
                    "guid": f"in.({filter_value})",
                },
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            for row in response.json():
                result[row["guid"]] = row.get("translation_status", "pending")
        return result

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

    def create_pipeline_run(
        self,
        *,
        job_type: str,
        status: str = "running",
        stats: dict[str, Any] | None = None,
    ) -> str | None:
        endpoint = f"{self.url}/rest/v1/pipeline_runs"
        payload = {
            "job_type": job_type,
            "status": status,
            "started_at": _now_iso(),
            "stats": stats or {},
        }
        response = self.session.post(
            endpoint,
            headers={
                **self._headers(),
                "content-type": "application/json",
                "prefer": "return=representation",
            },
            data=json.dumps([payload], ensure_ascii=False),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        return rows[0].get("id")

    def finish_pipeline_run(
        self,
        run_id: str,
        *,
        status: str,
        stats: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        endpoint = f"{self.url}/rest/v1/pipeline_runs"
        payload = {
            "status": status,
            "finished_at": _now_iso(),
            "stats": stats or {},
            "error": (error or "")[:2000] or None,
        }
        response = self.session.patch(
            endpoint,
            params={"id": f"eq.{run_id}"},
            headers={
                **self._headers(),
                "content-type": "application/json",
                "prefer": "return=minimal",
            },
            data=json.dumps(payload, ensure_ascii=False),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def fetch_pending_translation_items(self, *, limit: int = 200) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/news_items"
        response = self.session.get(
            endpoint,
            params={
                "select": "id,guid,title,summary,source_lang,translation_status",
                "translation_status": "eq.pending",
                "order": "published_at.desc.nullslast",
                "limit": str(limit),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def fetch_candidate_translation_items(
        self,
        *,
        digest_date: str,
        limit: int = 40,
        statuses: tuple[str, ...] = ("pending", "failed"),
    ) -> list[dict[str, Any]]:
        candidate_endpoint = f"{self.url}/rest/v1/digest_candidates"
        candidate_response = self.session.get(
            candidate_endpoint,
            params={
                "select": "representative_item_guid,rank",
                "digest_date": f"eq.{digest_date}",
                "order": "rank.asc",
                "limit": str(limit),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        candidate_response.raise_for_status()
        candidate_rows = candidate_response.json()
        if not candidate_rows:
            return []

        ranked_guids = [str(row.get("representative_item_guid") or "") for row in candidate_rows]
        ranked_guids = [guid for guid in ranked_guids if guid]
        if not ranked_guids:
            return []
        rank_map = {guid: index for index, guid in enumerate(ranked_guids)}

        filter_value = ",".join(f'"{guid}"' for guid in ranked_guids)
        status_filters = ",".join(f"translation_status.eq.{status}" for status in statuses if status)

        news_endpoint = f"{self.url}/rest/v1/news_items"
        params = {
            "select": "id,guid,title,summary,source_lang,translation_status",
            "guid": f"in.({filter_value})",
            "limit": str(max(limit * 2, 40)),
        }
        if status_filters:
            params["or"] = f"({status_filters})"

        response = self.session.get(
            news_endpoint,
            params=params,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        rows.sort(key=lambda row: rank_map.get(str(row.get("guid") or ""), 10**9))
        return rows

    def fetch_translation(self, source_hash: str) -> dict[str, Any] | None:
        endpoint = f"{self.url}/rest/v1/translations"
        response = self.session.get(
            endpoint,
            params={
                "select": "source_hash,source_lang,target_lang,translated_text,provider,model",
                "source_hash": f"eq.{source_hash}",
                "limit": "1",
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    def upsert_translation(
        self,
        *,
        source_hash: str,
        source_lang: str,
        target_lang: str,
        source_text: str,
        translated_text: str,
        provider: str,
        model: str,
        quality_score: float | None = None,
    ) -> None:
        self._upsert(
            "translations",
            [
                {
                    "source_hash": source_hash,
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "source_text": source_text,
                    "translated_text": translated_text,
                    "provider": provider,
                    "model": model,
                    "quality_score": quality_score,
                }
            ],
            on_conflict="source_hash",
        )

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

    def fetch_digest_items(
        self,
        *,
        start_at: str,
        end_at: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/news_items"
        response = self.session.get(
            endpoint,
            params=[
                (
                    "select",
                    "guid,source_id,source_lang,title,title_zh,summary,summary_zh,"
                    "url,external_url,published_at,translation_status",
                ),
                ("published_at", f"gte.{start_at}"),
                ("published_at", f"lt.{end_at}"),
                ("translation_status", "eq.translated"),
                ("order", "published_at.asc.nullslast"),
                ("limit", str(limit)),
            ],
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def upsert_daily_digest(self, row: dict[str, Any]) -> None:
        self._upsert("daily_digests", [row], on_conflict="digest_date")

    def fetch_news_items_for_window(
        self,
        *,
        start_at: str,
        end_at: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/news_items"
        response = self.session.get(
            endpoint,
            params=[
                (
                    "select",
                    "guid,source_id,source_lang,title,summary,url,external_url,published_at,content_hash",
                ),
                ("published_at", f"gte.{start_at}"),
                ("published_at", f"lt.{end_at}"),
                ("order", "published_at.desc.nullslast"),
                ("limit", str(limit)),
            ],
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def replace_clusters_for_date(
        self,
        *,
        digest_date: str,
        clusters: list[dict[str, Any]],
        members: list[dict[str, Any]],
    ) -> None:
        self._delete("intelligence_clusters", {"digest_date": f"eq.{digest_date}"})
        if clusters:
            self._upsert("intelligence_clusters", clusters, on_conflict="digest_date,cluster_key")
        if members:
            self._upsert("cluster_members", members, on_conflict="cluster_id,news_item_guid")

    def fetch_clusters_for_date(self, *, digest_date: str, limit: int = 500) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/intelligence_clusters"
        response = self.session.get(
            endpoint,
            params={
                "select": (
                    "id,digest_date,cluster_key,representative_item_guid,canonical_title,"
                    "canonical_url,source_ids,item_count,language_mix,importance_score,status"
                ),
                "digest_date": f"eq.{digest_date}",
                "order": "importance_score.desc,item_count.desc",
                "limit": str(limit),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def replace_digest_candidates_for_date(
        self,
        *,
        digest_date: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        self._delete("digest_candidates", {"digest_date": f"eq.{digest_date}"})
        if candidates:
            self._upsert("digest_candidates", candidates, on_conflict="digest_date,cluster_id")

    def fetch_digest_candidate_items(
        self,
        *,
        digest_date: str,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        candidate_endpoint = f"{self.url}/rest/v1/digest_candidates"
        candidate_response = self.session.get(
            candidate_endpoint,
            params={
                "select": "representative_item_guid,rank",
                "digest_date": f"eq.{digest_date}",
                "order": "rank.asc",
                "limit": str(limit),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        candidate_response.raise_for_status()
        candidate_rows = candidate_response.json()
        if not candidate_rows:
            return []

        ranked_guids = [str(row.get("representative_item_guid") or "") for row in candidate_rows]
        ranked_guids = [guid for guid in ranked_guids if guid]
        if not ranked_guids:
            return []
        meta_map: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(candidate_rows):
            guid = str(row.get("representative_item_guid") or "")
            if not guid:
                continue
            meta_map[guid] = {
                "_candidate_rank": int(row.get("rank") or index + 1),
                "_candidate_importance_score": float(row.get("importance_score") or 0.0),
                "_candidate_source_ids": row.get("source_ids") or [],
                "_candidate_cluster_id": row.get("cluster_id") or "",
            }

        rank_map = {guid: meta_map[guid]["_candidate_rank"] for guid in ranked_guids if guid in meta_map}
        filter_value = ",".join(f'"{guid}"' for guid in ranked_guids)

        news_endpoint = f"{self.url}/rest/v1/news_items"
        response = self.session.get(
            news_endpoint,
            params={
                "select": (
                    "guid,source_id,source_lang,title,title_zh,summary,summary_zh,"
                    "url,external_url,published_at,translation_status"
                ),
                "guid": f"in.({filter_value})",
                "limit": str(max(limit * 2, 80)),
            },
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json()
        for row in rows:
            guid = str(row.get("guid") or "")
            if guid in meta_map:
                row.update(meta_map[guid])
        rows.sort(key=lambda row: rank_map.get(str(row.get("guid") or ""), 10**9))
        return rows

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "authorization": f"Bearer {self.service_role_key}",
        }

    def _delete(self, table: str, filters: dict[str, str]) -> None:
        endpoint = f"{self.url}/rest/v1/{table}"
        response = self.session.delete(
            endpoint,
            params=filters,
            headers={
                **self._headers(),
                "prefer": "return=minimal",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()


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
