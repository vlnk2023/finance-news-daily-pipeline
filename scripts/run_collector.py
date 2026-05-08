"""Run one-shot Telegram collection from the feed registry."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.config import load_enabled_feeds
from collector.async_runner import AsyncCollectionRunner, FeedCollectionError
from collector.runner import CollectionRunner
from collector.storage.supabase_store import SupabaseStore
from scripts.pipeline_run_tracker import track_pipeline_run


DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "src/config/feed-registry.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Telegram feed collection once.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--feed-id", help="Collect only one feed_id.")
    parser.add_argument(
        "--async",
        dest="run_async",
        action="store_true",
        help="Collect feeds concurrently.",
    )
    parser.add_argument("--max-concurrency", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Print collected items as JSON.")
    parser.add_argument(
        "--results-json",
        action="store_true",
        help="Print full collection results as JSON.",
    )
    parser.add_argument(
        "--write-supabase",
        action="store_true",
        help="Upsert successful collection results into Supabase.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    with track_pipeline_run(
        "collect",
        initial_stats={
            "mode": "async" if args.run_async else "sync",
            "write_supabase": bool(args.write_supabase),
            "feed_id": args.feed_id or "",
        },
    ) as run_stats:
        feeds = load_enabled_feeds(args.registry, platform="telegram")
        if args.feed_id:
            feeds = [feed for feed in feeds if feed.get("feed_id") == args.feed_id]

        if args.run_async:
            results = asyncio.run(
                AsyncCollectionRunner(max_concurrency=args.max_concurrency).collect_feeds(feeds)
            )
        else:
            results = CollectionRunner().collect_feeds(feeds)

        total_fetched = sum(r.fetched_count for r in results if not isinstance(r, FeedCollectionError))
        total_returned = sum(r.returned_count for r in results if not isinstance(r, FeedCollectionError))
        total_duplicates = sum(r.duplicate_count for r in results if not isinstance(r, FeedCollectionError))
        error_count = sum(1 for result in results if isinstance(result, FeedCollectionError))
        run_stats.update(
            {
                "feeds": len(feeds),
                "results": len(results),
                "total_fetched": total_fetched,
                "total_returned": total_returned,
                "total_duplicates": total_duplicates,
                "error_count": error_count,
            }
        )
        print(f"[COLLECT] feeds={len(feeds)} results={len(results)} total_fetched={total_fetched} total_returned={total_returned} total_duplicates={total_duplicates}")

        successful_results = [
            result for result in results if not isinstance(result, FeedCollectionError)
        ]
        if args.write_supabase:
            feeds_by_id = {feed["feed_id"]: feed for feed in feeds}
            stats = SupabaseStore().upsert_results(successful_results, feeds_by_id=feeds_by_id)
            run_stats.update(
                {
                    "sources_upserted": stats.sources_upserted,
                    "items_upserted": stats.items_upserted,
                }
            )
            print(f"[COLLECT] Supabase write complete sources={stats.sources_upserted} items={stats.items_upserted}")
            logging.info(
                "Supabase write complete sources=%s items=%s",
                stats.sources_upserted,
                stats.items_upserted,
            )

        if args.results_json:
            print(
                json.dumps(
                    [result.to_dict() for result in results],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        if args.json:
            items = [
                item
                for result in successful_results
                for item in result.items
            ]
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return

        for result in results:
            if isinstance(result, FeedCollectionError):
                print(f"{result.feed_id}: failed error={result.error}")
                continue
            print(
                f"{result.feed_id}: fetched={result.fetched_count} "
                f"returned={result.returned_count} duplicates={result.duplicate_count} "
                f"elapsed_ms={result.elapsed_ms} attempts={result.attempts}"
            )
            for item in result.items:
                print(item["title"])
                print(item["pub_str"])
                print(item["url"])
                print("---")


if __name__ == "__main__":
    main()
