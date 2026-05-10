"""Async orchestration for running multiple feed collections concurrently."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from collector.fetchers.telegram_fetcher import TelegramFetcher
from collector.rate_limiter import InProcessRateLimiter, RateLimiter
from collector.runner import CollectionRunner, FeedCollectionResult


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedCollectionError:
    """Collection failure for a single feed."""

    feed_id: str
    source_id: str
    url: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {
            "feed_id": self.feed_id,
            "source_id": self.source_id,
            "url": self.url,
            "error": self.error,
        }


class AsyncCollectionRunner:
    """Run multiple feed collections concurrently without changing storage."""

    def __init__(
        self,
        *,
        max_concurrency: int = 5,
        runner_factory: Any = CollectionRunner,
        min_interval_seconds: float = 1.0,
        shared_rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.max_concurrency = max(max_concurrency, 1)
        self.runner_factory = runner_factory
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self.shared_rate_limiter = shared_rate_limiter or InProcessRateLimiter(
            self.min_interval_seconds
        )

    async def collect_feeds(
        self,
        feeds: list[dict[str, Any]],
    ) -> list[FeedCollectionResult | FeedCollectionError]:
        semaphore = asyncio.Semaphore(self.max_concurrency)
        executor = ThreadPoolExecutor(max_workers=self.max_concurrency)

        async def guarded_collect(feed: dict[str, Any]) -> FeedCollectionResult | FeedCollectionError:
            async with semaphore:
                return await self.collect_feed(feed, executor=executor)

        try:
            tasks = [guarded_collect(feed) for feed in feeds if self._should_collect(feed)]
            return await asyncio.gather(*tasks)
        finally:
            executor.shutdown(wait=True)

    async def collect_feed(
        self,
        feed: dict[str, Any],
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> FeedCollectionResult | FeedCollectionError:
        try:
            runner = self._build_runner()
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, runner.collect_feed, feed)
        except Exception as exc:
            LOGGER.exception("feed collection failed feed_id=%s", feed.get("feed_id"))
            return FeedCollectionError(
                feed_id=feed.get("feed_id", ""),
                source_id=feed.get("source_id", ""),
                url=feed.get("url", ""),
                error=str(exc),
            )

    def _should_collect(self, feed: dict[str, Any]) -> bool:
        return feed.get("enabled", True) and feed.get("platform") == "telegram"

    def _build_runner(self) -> Any:
        fetcher = TelegramFetcher(
            min_interval_seconds=self.min_interval_seconds,
            rate_limiter=self.shared_rate_limiter,
        )
        try:
            return self.runner_factory(fetcher=fetcher)
        except TypeError:
            # Compatibility path for test fakes or custom runner factories that
            # do not accept keyword dependencies.
            return self.runner_factory()
