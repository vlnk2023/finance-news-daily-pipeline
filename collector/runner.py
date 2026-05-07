"""Collection runner that wires feed config, fetcher and parser together."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from collector.fetchers.telegram_fetcher import TelegramFetcher
from collector.parsers.telegram_parser import TelegramParser


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedCollectionResult:
    """Result for one feed collection attempt."""

    feed_id: str
    source_id: str
    url: str
    fetched_count: int
    returned_count: int
    duplicate_count: int
    elapsed_ms: int
    attempts: int
    items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed_id": self.feed_id,
            "source_id": self.source_id,
            "url": self.url,
            "fetched_count": self.fetched_count,
            "returned_count": self.returned_count,
            "duplicate_count": self.duplicate_count,
            "elapsed_ms": self.elapsed_ms,
            "attempts": self.attempts,
            "items": self.items,
        }


class CollectionRunner:
    """Run one-shot collection for Telegram feeds without owning storage."""

    def __init__(
        self,
        *,
        fetcher: TelegramFetcher | None = None,
        parser: TelegramParser | None = None,
    ) -> None:
        self.fetcher = fetcher or TelegramFetcher()
        self.parser = parser or TelegramParser()

    def collect_feed(self, feed: dict[str, Any]) -> FeedCollectionResult:
        collect_config = feed.get("collect", {}) or {}
        timeout_ms = int(collect_config.get("timeout_ms", 12000))
        retries = int(collect_config.get("retries", 2))
        max_items = int(collect_config.get("max_items_per_run", 20))
        lookback_hours = collect_config.get("lookback_hours")

        fetch_result = self.fetcher.fetch(
            feed["url"],
            timeout_ms=timeout_ms,
            retries=retries,
        )
        parsed_items = self.parser.parse(fetch_result.html)
        enriched_items = [self._enrich_item(item, feed) for item in parsed_items]
        filtered_items = self._filter_by_lookback(enriched_items, lookback_hours)
        unique_items = self._dedupe_within_run(filtered_items)
        limited_items = unique_items[:max_items]

        duplicate_count = len(filtered_items) - len(unique_items)
        result = FeedCollectionResult(
            feed_id=feed["feed_id"],
            source_id=feed["source_id"],
            url=feed["url"],
            fetched_count=len(parsed_items),
            returned_count=len(limited_items),
            duplicate_count=duplicate_count,
            elapsed_ms=fetch_result.elapsed_ms,
            attempts=fetch_result.attempts,
            items=limited_items,
        )
        LOGGER.info(
            "feed collected feed_id=%s fetched=%s returned=%s duplicates=%s elapsed_ms=%s attempts=%s",
            result.feed_id,
            result.fetched_count,
            result.returned_count,
            result.duplicate_count,
            result.elapsed_ms,
            result.attempts,
        )
        return result

    def collect_feeds(self, feeds: list[dict[str, Any]]) -> list[FeedCollectionResult]:
        results: list[FeedCollectionResult] = []
        for feed in feeds:
            if feed.get("platform") != "telegram":
                LOGGER.info("skipping non-Telegram feed feed_id=%s", feed.get("feed_id"))
                continue
            if not feed.get("enabled", True):
                LOGGER.info("skipping disabled feed feed_id=%s", feed.get("feed_id"))
                continue
            results.append(self.collect_feed(feed))
        return results

    def _enrich_item(self, item: dict[str, Any], feed: dict[str, Any]) -> dict[str, Any]:
        message_id = item.get("guid", "")
        enriched = {
            **item,
            "source_id": feed["source_id"],
            "source_name": feed["source_name"],
            "feed_id": feed["feed_id"],
            "platform": feed["platform"],
            "message_id": message_id,
            "guid": f"{feed['source_id']}:{message_id}" if message_id else "",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        return enriched

    def _filter_by_lookback(
        self,
        items: list[dict[str, Any]],
        lookback_hours: Any,
    ) -> list[dict[str, Any]]:
        if lookback_hours in (None, "", 0):
            return items

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=float(lookback_hours))
        except (TypeError, ValueError):
            LOGGER.warning("invalid lookback_hours=%r; keeping all items", lookback_hours)
            return items

        kept = []
        for item in items:
            published_at = self._parse_datetime(item.get("pub_str", ""))
            if published_at is None or published_at >= cutoff:
                kept.append(item)
        return kept

    def _dedupe_within_run(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique_items: list[dict[str, Any]] = []
        for item in items:
            key = item.get("guid") or item.get("url")
            if not key:
                unique_items.append(item)
                continue
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        return unique_items

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            LOGGER.warning("invalid item pub_str=%r", value)
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
