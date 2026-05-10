import json
import tempfile
import unittest
from pathlib import Path

from collector.config.feed_registry import FeedRegistry, load_enabled_feeds


class FeedRegistryTest(unittest.TestCase):
    def test_load_enabled_feeds_filters_platform_and_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "feed-registry.json"
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "feed_id": "tg_enabled",
                            "source_id": "tg_enabled",
                            "source_name": "Enabled",
                            "platform": "telegram",
                            "url": "https://t.me/s/enabled",
                            "enabled": True,
                        },
                        {
                            "feed_id": "tg_disabled",
                            "source_id": "tg_disabled",
                            "source_name": "Disabled",
                            "platform": "telegram",
                            "url": "https://t.me/s/disabled",
                            "enabled": False,
                        },
                        {
                            "feed_id": "rss_enabled",
                            "source_id": "rss_enabled",
                            "source_name": "RSS",
                            "platform": "rss",
                            "url": "https://example.com/rss.xml",
                            "enabled": True,
                        },
                    ]
                ),
                encoding="utf-8",
            )

            feeds = load_enabled_feeds(registry_path, platform="telegram")

        self.assertEqual([feed["feed_id"] for feed in feeds], ["tg_enabled"])

    def test_feed_registry_rejects_missing_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "feed-registry.json"
            registry_path.write_text(json.dumps([{"feed_id": "bad"}]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required fields"):
                FeedRegistry.from_path(registry_path)

    def test_feed_registry_rejects_invalid_health_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "feed-registry.json"
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "feed_id": "tg_enabled",
                            "source_id": "tg_enabled",
                            "source_name": "Enabled",
                            "platform": "telegram",
                            "url": "https://t.me/s/enabled",
                            "health": {"expected_update_interval_hours": -1},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "health.expected_update_interval_hours"):
                FeedRegistry.from_path(registry_path)


if __name__ == "__main__":
    unittest.main()
