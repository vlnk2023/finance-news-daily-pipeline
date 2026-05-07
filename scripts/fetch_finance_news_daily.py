"""Fetch and print parsed Finance News Daily Telegram messages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.fetchers.telegram_fetcher import TelegramFetcher
from collector.parsers.telegram_parser import TelegramParser


DEFAULT_URL = "https://t.me/s/FinanceNewsDaily"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Telegram static channel page and parse messages."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    fetch_result = TelegramFetcher().fetch(
        args.url,
        timeout_ms=int(args.timeout * 1000),
        retries=args.retries,
    )
    items = TelegramParser().parse(fetch_result.html)[: args.limit]

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return

    for item in items:
        print(item["title"])
        print(item["summary"])
        print(item["pub_str"])
        print(item["url"])
        print("---")


if __name__ == "__main__":
    main()
