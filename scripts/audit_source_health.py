"""Audit source freshness and write source health telemetry."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.config import FeedRegistry
from collector.storage.supabase_store import SupabaseStore
from scripts.pipeline_run_tracker import track_pipeline_run


DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "src/config/feed-registry.json"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_EXPECTED_INTERVAL_BY_CADENCE = {
    "active_daily": 48,
    "active_weekly": 240,
    "low_frequency": 720,
    "dormant": 2160,
}


@dataclass(frozen=True)
class SourceHealth:
    feed_id: str
    source_id: str
    status: str
    cadence: str
    expected_update_interval_hours: float
    stale_after_hours: float
    latest_published_at: str
    age_hours: float | None
    item_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed_id": self.feed_id,
            "source_id": self.source_id,
            "status": self.status,
            "cadence": self.cadence,
            "expected_update_interval_hours": self.expected_update_interval_hours,
            "stale_after_hours": self.stale_after_hours,
            "latest_published_at": self.latest_published_at,
            "age_hours": self.age_hours,
            "item_count": self.item_count,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit source freshness from collected data.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD for run tracking.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--include-disabled", action="store_true")
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    now_utc = datetime.now(timezone.utc)
    feeds = FeedRegistry.from_path(args.registry).feeds
    if not args.include_disabled:
        feeds = [feed for feed in feeds if feed.get("enabled", True)]

    with track_pipeline_run(
        "audit_source_health",
        initial_stats={
            "digest_date": digest_date.isoformat(),
            "include_disabled": bool(args.include_disabled),
            "feeds": len(feeds),
        },
    ) as run_stats:
        store = SupabaseStore()
        records = [audit_feed_health(store, feed, now_utc=now_utc) for feed in feeds]
        counts = Counter(record.status for record in records)
        run_stats.update(
            {
                "source_health_counts": dict(counts),
                "source_health": [record.to_dict() for record in records],
            }
        )
        print(
            json.dumps(
                {
                    "digest_date": digest_date.isoformat(),
                    "source_health_counts": dict(counts),
                    "sources": [record.to_dict() for record in records],
                },
                ensure_ascii=False,
            )
        )


def audit_feed_health(
    store: SupabaseStore,
    feed: dict[str, Any],
    *,
    now_utc: datetime,
) -> SourceHealth:
    feed_id = str(feed.get("feed_id") or "")
    source_id = str(feed.get("source_id") or feed_id)
    enabled = bool(feed.get("enabled", True))
    if not enabled:
        return SourceHealth(
            feed_id=feed_id,
            source_id=source_id,
            status="disabled",
            cadence="disabled",
            expected_update_interval_hours=0.0,
            stale_after_hours=0.0,
            latest_published_at="",
            age_hours=None,
            item_count=0,
        )

    latest_published_at, item_count = fetch_source_latest_and_count(store, source_id)
    cadence, expected_hours, stale_after_hours = resolve_health_policy(feed)
    status, age_hours = classify_source_health(
        latest_published_at,
        item_count,
        now_utc=now_utc,
        expected_update_interval_hours=expected_hours,
        stale_after_hours=stale_after_hours,
    )
    return SourceHealth(
        feed_id=feed_id,
        source_id=source_id,
        status=status,
        cadence=cadence,
        expected_update_interval_hours=expected_hours,
        stale_after_hours=stale_after_hours,
        latest_published_at=latest_published_at,
        age_hours=age_hours,
        item_count=item_count,
    )


def fetch_source_latest_and_count(store: SupabaseStore, source_id: str) -> tuple[str, int]:
    endpoint = f"{store.url}/rest/v1/news_items"
    response = store.session.get(
        endpoint,
        params={
            "select": "published_at",
            "source_id": f"eq.{source_id}",
            "order": "published_at.desc.nullslast",
            "limit": "1",
        },
        headers={**store._headers(), "prefer": "count=exact"},
        timeout=store.timeout_seconds,
    )
    response.raise_for_status()
    content_range = response.headers.get("content-range", "")
    item_count = parse_content_range_count(content_range)
    rows = response.json()
    latest_published_at = str(rows[0].get("published_at") or "") if rows else ""
    return latest_published_at, item_count


def resolve_health_policy(feed: dict[str, Any]) -> tuple[str, float, float]:
    health = feed.get("health") or {}
    cadence = str(health.get("cadence") or infer_cadence(feed))
    expected_hours = float(
        health.get("expected_update_interval_hours")
        or DEFAULT_EXPECTED_INTERVAL_BY_CADENCE.get(cadence, 720)
    )
    stale_after_hours = float(health.get("stale_after_hours") or (expected_hours * 2.0))
    return cadence, expected_hours, stale_after_hours


def infer_cadence(feed: dict[str, Any]) -> str:
    collect = feed.get("collect") or {}
    runs_per_day = int(collect.get("runs_per_day") or 0)
    if runs_per_day >= 2:
        return "active_daily"
    if runs_per_day == 1:
        return "active_weekly"
    return "low_frequency"


def classify_source_health(
    latest_published_at: str,
    item_count: int,
    *,
    now_utc: datetime,
    expected_update_interval_hours: float,
    stale_after_hours: float,
) -> tuple[str, float | None]:
    if item_count <= 0:
        return "no_data", None

    latest_dt = parse_iso_datetime(latest_published_at)
    if latest_dt is None:
        return "unknown", None

    age_hours = max((now_utc - latest_dt).total_seconds() / 3600.0, 0.0)
    if age_hours <= expected_update_interval_hours:
        return "healthy_active", round(age_hours, 3)
    if age_hours <= stale_after_hours:
        return "healthy_quiet", round(age_hours, 3)
    return "stale", round(age_hours, 3)


def parse_iso_datetime(value: str) -> datetime | None:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_content_range_count(content_range: str) -> int:
    if "/" not in content_range:
        return 0
    suffix = content_range.split("/")[-1].strip()
    if not suffix or suffix == "*":
        return 0
    try:
        return int(suffix)
    except ValueError:
        return 0


if __name__ == "__main__":
    main()
