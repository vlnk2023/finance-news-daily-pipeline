"""Load and validate feed registry entries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "src/config/feed-registry.json"


@dataclass(frozen=True)
class FeedRegistry:
    """Feed registry loaded from JSON configuration."""

    feeds: list[dict[str, Any]]

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_REGISTRY_PATH) -> "FeedRegistry":
        registry_path = Path(path)
        with registry_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError("feed registry must be a JSON list")

        feeds = []
        for index, feed in enumerate(data):
            if not isinstance(feed, dict):
                raise ValueError(f"feed registry item {index} must be an object")
            _validate_feed(feed, index)
            feeds.append(feed)

        return cls(feeds=feeds)

    def enabled_feeds(self, platform: str | None = None) -> list[dict[str, Any]]:
        feeds = [feed for feed in self.feeds if feed.get("enabled", True)]
        if platform:
            feeds = [feed for feed in feeds if feed.get("platform") == platform]
        return feeds


def load_enabled_feeds(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    platform: str | None = None,
) -> list[dict[str, Any]]:
    return FeedRegistry.from_path(path).enabled_feeds(platform=platform)


def _validate_feed(feed: dict[str, Any], index: int) -> None:
    required = ("feed_id", "source_id", "source_name", "platform", "url")
    missing = [field for field in required if not feed.get(field)]
    if missing:
        fields = ", ".join(missing)
        raise ValueError(f"feed registry item {index} missing required fields: {fields}")

    collect = feed.get("collect", {})
    if collect is not None and not isinstance(collect, dict):
        raise ValueError(f"feed registry item {index} collect must be an object")

