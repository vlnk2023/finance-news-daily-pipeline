"""Advance news item translation state in Supabase.

This first version provides the pipeline state machine: Chinese items are copied
into the normalized Chinese fields, while non-Chinese items are tagged with a
detected language and left pending for a later external translation engine.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore
from collector.translation import detect_language, is_chinese


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending news item translations.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    store = SupabaseStore()
    items = store.fetch_pending_translation_items(limit=args.limit)
    stats = {"fetched": len(items), "zh_completed": 0, "pending_external": 0}

    for item in items:
        text = "\n".join(
            part for part in [item.get("title") or "", item.get("summary") or ""] if part
        )
        source_lang = detect_language(text)
        fields = {"source_lang": source_lang}
        if is_chinese(source_lang):
            fields.update(
                {
                    "title_zh": item.get("title") or "",
                    "summary_zh": item.get("summary") or "",
                    "translation_status": "translated",
                }
            )
            stats["zh_completed"] += 1
        else:
            stats["pending_external"] += 1

        store.update_news_item(item["id"], fields)

    logging.info(
        "translation state processed fetched=%s zh_completed=%s pending_external=%s",
        stats["fetched"],
        stats["zh_completed"],
        stats["pending_external"],
    )


if __name__ == "__main__":
    main()
