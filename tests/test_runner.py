import unittest

from collector.fetchers.telegram_fetcher import FetchResult
from collector.runner import CollectionRunner


class FakeFetcher:
    def fetch(self, url, *, timeout_ms, retries):
        assert url == "https://t.me/s/FinanceNewsDaily"
        assert timeout_ms == 12000
        assert retries == 2
        return FetchResult(
            url=url,
            html="<html></html>",
            status_code=200,
            elapsed_ms=25,
            attempts=1,
        )


class FakeParser:
    def parse(self, html):
        assert html == "<html></html>"
        return [
            {
                "title": "A",
                "url": "https://t.me/FinanceNewsDaily/100",
                "summary": "A body",
                "pub_str": "2999-05-05T08:30:00+00:00",
                "guid": "100",
                "external_url": "",
                "preview_title": "",
                "raw_text_full": "A body",
            },
            {
                "title": "A duplicate",
                "url": "https://t.me/FinanceNewsDaily/100",
                "summary": "A duplicate body",
                "pub_str": "2999-05-05T08:30:00+00:00",
                "guid": "100",
                "external_url": "",
                "preview_title": "",
                "raw_text_full": "A duplicate body",
            },
            {
                "title": "Old",
                "url": "https://t.me/FinanceNewsDaily/99",
                "summary": "Old body",
                "pub_str": "2020-01-01T00:00:00+00:00",
                "guid": "99",
                "external_url": "",
                "preview_title": "",
                "raw_text_full": "Old body",
            },
        ]


class CollectionRunnerTest(unittest.TestCase):
    def test_collect_feed_enriches_filters_dedupes_and_limits(self) -> None:
        feed = {
            "feed_id": "tg_finance_news_daily",
            "source_id": "tg_finance_news_daily",
            "source_name": "Finance News Daily",
            "platform": "telegram",
            "url": "https://t.me/s/FinanceNewsDaily",
            "collect": {
                "timeout_ms": 12000,
                "retries": 2,
                "lookback_hours": 48,
                "max_items_per_run": 1,
            },
        }
        runner = CollectionRunner(fetcher=FakeFetcher(), parser=FakeParser())

        result = runner.collect_feed(feed)

        self.assertEqual(result.feed_id, "tg_finance_news_daily")
        self.assertEqual(result.fetched_count, 3)
        self.assertEqual(result.returned_count, 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(result.elapsed_ms, 25)
        self.assertEqual(result.items[0]["message_id"], "100")
        self.assertEqual(result.items[0]["guid"], "tg_finance_news_daily:100")
        self.assertEqual(result.items[0]["source_name"], "Finance News Daily")
        self.assertEqual(result.to_dict()["returned_count"], 1)


if __name__ == "__main__":
    unittest.main()
