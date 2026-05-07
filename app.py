from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_ROOT = PROJECT_ROOT / ".cache"
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_ROOT / "matplotlib"))
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from collector.config import load_enabled_feeds
from collector.runner import CollectionRunner


REGISTRY_PATH = PROJECT_ROOT / "src" / "config" / "feed-registry.json"


def _load_feeds() -> list[dict[str, Any]]:
    try:
        return load_enabled_feeds(REGISTRY_PATH, platform="telegram")
    except Exception:
        return []


FEEDS = _load_feeds()
FEED_BY_ID = {feed["feed_id"]: feed for feed in FEEDS}
DEFAULT_FEED_ID = FEEDS[0]["feed_id"] if FEEDS else ""


def _normalize_telegram_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("https://t.me/") and not normalized.startswith("https://t.me/s/"):
        channel = normalized.removeprefix("https://t.me/").strip("/")
        if "/" not in channel:
            return f"https://t.me/s/{channel}"
    return normalized


def _item_rows(items: list[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for item in items:
        rows.append(
            [
                item.get("title", ""),
                item.get("pub_str", ""),
                item.get("url", ""),
                item.get("external_url", ""),
                item.get("summary", ""),
            ]
        )
    return rows


def _selected_feed(feed_id: str, custom_url: str, limit: int, timeout_seconds: int, retries: int) -> dict[str, Any]:
    base_feed = dict(FEED_BY_ID.get(feed_id) or next(iter(FEED_BY_ID.values()), {}))
    if not base_feed:
        base_feed = {
            "feed_id": "custom_telegram_feed",
            "source_id": "custom_telegram_feed",
            "source_name": "Custom Telegram Feed",
            "platform": "telegram",
            "url": "https://t.me/s/FinanceNewsDaily",
            "enabled": True,
        }

    url = _normalize_telegram_url(custom_url) if custom_url.strip() else base_feed["url"]
    collect = dict(base_feed.get("collect", {}) or {})
    collect.update(
        {
            "max_items_per_run": int(limit),
            "timeout_ms": int(timeout_seconds) * 1000,
            "retries": int(retries),
        }
    )
    base_feed.update({"url": url, "collect": collect})
    return base_feed


def collect(feed_id: str, custom_url: str, limit: int, timeout_seconds: int, retries: int) -> tuple[str, list[list[str]], str]:
    feed = _selected_feed(feed_id, custom_url, limit, timeout_seconds, retries)
    try:
        result = CollectionRunner().collect_feed(feed)
    except Exception as exc:
        status = f"Collection failed: {exc}"
        return status, [], json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)

    status = (
        f"Fetched {result.fetched_count} messages, returned {result.returned_count}, "
        f"duplicates {result.duplicate_count}, elapsed {result.elapsed_ms} ms, attempts {result.attempts}."
    )
    return status, _item_rows(result.items), json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


with gr.Blocks(title="Finance News Daily Collector") as demo:
    gr.Markdown("# Finance News Daily Collector")
    with gr.Row():
        feed = gr.Dropdown(
            choices=list(FEED_BY_ID.keys()) or ["custom_telegram_feed"],
            value=DEFAULT_FEED_ID or "custom_telegram_feed",
            label="Feed",
        )
        limit = gr.Slider(1, 50, value=20, step=1, label="Limit")
    custom_url = gr.Textbox(
        label="Custom Telegram URL",
        placeholder="https://t.me/s/FinanceNewsDaily",
    )
    with gr.Row():
        timeout_seconds = gr.Slider(3, 30, value=12, step=1, label="Timeout seconds")
        retries = gr.Slider(0, 5, value=2, step=1, label="Retries")
    run = gr.Button("Collect", variant="primary")
    status = gr.Markdown()
    table = gr.Dataframe(
        headers=["Title", "Published", "Telegram URL", "External URL", "Summary"],
        datatype=["str", "str", "str", "str", "str"],
        wrap=True,
        interactive=False,
    )
    raw_json = gr.Code(label="Raw JSON", language="json")

    run.click(
        fn=collect,
        inputs=[feed, custom_url, limit, timeout_seconds, retries],
        outputs=[status, table, raw_json],
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or "7860")
    server_name = os.environ.get("GRADIO_SERVER_NAME")
    if not server_name:
        server_name = "0.0.0.0" if os.environ.get("SPACE_ID") else "127.0.0.1"
    demo.launch(server_name=server_name, server_port=port, prevent_thread_lock=True)
    while True:
        time.sleep(3600)
