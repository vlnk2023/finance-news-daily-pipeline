import logging
import threading
import unittest

from collector.async_runner import AsyncCollectionRunner, FeedCollectionError
from collector.runner import FeedCollectionResult


class FakeRunner:
    def collect_feed(self, feed):
        if feed["feed_id"] == "bad":
            raise RuntimeError("network failed")
        return FeedCollectionResult(
            feed_id=feed["feed_id"],
            source_id=feed["source_id"],
            url=feed["url"],
            fetched_count=1,
            returned_count=1,
            duplicate_count=0,
            elapsed_ms=10,
            attempts=1,
            items=[],
        )


class CountingRateLimiter:
    def __init__(self) -> None:
        self.wait_calls = 0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            self.wait_calls += 1


class RunnerUsesFetcher:
    def __init__(self, *, fetcher) -> None:
        self.fetcher = fetcher

    def collect_feed(self, feed):
        self.fetcher.rate_limiter.wait()
        return FeedCollectionResult(
            feed_id=feed["feed_id"],
            source_id=feed["source_id"],
            url=feed["url"],
            fetched_count=1,
            returned_count=1,
            duplicate_count=0,
            elapsed_ms=10,
            attempts=1,
            items=[],
        )


class AsyncCollectionRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_collect_feeds_returns_results_and_errors(self) -> None:
        feeds = [
            {
                "feed_id": "good",
                "source_id": "good",
                "source_name": "Good",
                "platform": "telegram",
                "url": "https://t.me/s/good",
                "enabled": True,
            },
            {
                "feed_id": "bad",
                "source_id": "bad",
                "source_name": "Bad",
                "platform": "telegram",
                "url": "https://t.me/s/bad",
                "enabled": True,
            },
            {
                "feed_id": "disabled",
                "source_id": "disabled",
                "source_name": "Disabled",
                "platform": "telegram",
                "url": "https://t.me/s/disabled",
                "enabled": False,
            },
        ]
        runner = AsyncCollectionRunner(max_concurrency=2, runner_factory=FakeRunner)

        logging.disable(logging.CRITICAL)
        try:
            results = await runner.collect_feeds(feeds)
        finally:
            logging.disable(logging.NOTSET)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].feed_id, "good")
        self.assertIsInstance(results[1], FeedCollectionError)
        self.assertEqual(results[1].feed_id, "bad")
        self.assertIn("network failed", results[1].error)
        self.assertIn("network failed", results[1].to_dict()["error"])

    async def test_collect_feeds_shares_rate_limiter_across_feeds(self) -> None:
        limiter = CountingRateLimiter()
        feeds = [
            {
                "feed_id": "f1",
                "source_id": "f1",
                "source_name": "F1",
                "platform": "telegram",
                "url": "https://t.me/s/f1",
                "enabled": True,
            },
            {
                "feed_id": "f2",
                "source_id": "f2",
                "source_name": "F2",
                "platform": "telegram",
                "url": "https://t.me/s/f2",
                "enabled": True,
            },
        ]
        runner = AsyncCollectionRunner(
            max_concurrency=2,
            runner_factory=RunnerUsesFetcher,
            shared_rate_limiter=limiter,
        )

        results = await runner.collect_feeds(feeds)

        self.assertEqual(len(results), 2)
        self.assertEqual(limiter.wait_calls, 2)


if __name__ == "__main__":
    unittest.main()
