"""Translate pending news items and update normalized Chinese fields."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore
from collector.translation import detect_language, is_chinese
from collector.translation.cloudflare import (
    DEFAULT_MODEL,
    CloudflareTranslationError,
    CloudflareTranslator,
)


TARGET_LANG = "zh"


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending news item translations.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--provider",
        choices=["cloudflare", "state-only"],
        default=os.environ.get("TRANSLATION_PROVIDER", "cloudflare"),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    store = SupabaseStore()
    translator = None
    if args.provider == "cloudflare":
        try:
            translator = CloudflareTranslator()
            print("[TRANSLATE] CloudflareTranslator initialized OK")
        except Exception as exc:
            print(f"[TRANSLATE] CloudflareTranslator init FAILED: {exc}")
            logging.error("CloudflareTranslator init failed: %s", exc)

    items = store.fetch_pending_translation_items(limit=args.limit)
    print(f"[TRANSLATE] fetched {len(items)} pending items from Supabase")
    stats = {
        "fetched": len(items),
        "zh_completed": 0,
        "cache_hits": 0,
        "cloudflare_translated": 0,
        "pending_external": 0,
        "failed": 0,
    }

    for item in items:
        text = "\n".join(
            part for part in [item.get("title") or "", item.get("summary") or ""] if part
        )
        source_lang = item.get("source_lang") or detect_language(text)
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
            if translator is None:
                stats["pending_external"] += 1
            else:
                try:
                    fields.update(
                        {
                            "title_zh": _translate_text(
                                store,
                                translator,
                                item.get("title") or "",
                                source_lang=source_lang,
                                stats=stats,
                            ),
                            "summary_zh": _translate_text(
                                store,
                                translator,
                                item.get("summary") or "",
                                source_lang=source_lang,
                                stats=stats,
                            ),
                            "translation_status": "translated",
                        }
                    )
                    stats["cloudflare_translated"] += 1
                except Exception as exc:
                    logging.exception("translation failed guid=%s", item.get("guid"))
                    fields.update(
                        {
                            "translation_status": "failed",
                        }
                    )
                    stats["failed"] += 1

        store.update_news_item(item["id"], fields)

    print(
        f"[TRANSLATE] done fetched={stats['fetched']} zh_completed={stats['zh_completed']} "
        f"cloudflare_translated={stats['cloudflare_translated']} cache_hits={stats['cache_hits']} "
        f"failed={stats['failed']} pending_external={stats['pending_external']}"
    )
    logging.info(
        (
            "translation processed fetched=%s zh_completed=%s cache_hits=%s "
            "cloudflare_translated=%s pending_external=%s failed=%s"
        ),
        stats["fetched"],
        stats["zh_completed"],
        stats["cache_hits"],
        stats["cloudflare_translated"],
        stats["pending_external"],
        stats["failed"],
    )


def _translate_text(
    store: SupabaseStore,
    translator: CloudflareTranslator,
    text: str,
    *,
    source_lang: str,
    stats: dict[str, int],
) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""

    source_hash = _text_hash(normalized, source_lang, TARGET_LANG)
    cached = store.fetch_translation(source_hash)
    if cached:
        stats["cache_hits"] += 1
        return cached["translated_text"]

    translated = translator.translate(
        normalized,
        source_lang=source_lang,
        target_lang=TARGET_LANG,
    )
    store.upsert_translation(
        source_hash=source_hash,
        source_lang=source_lang,
        target_lang="zh-Hans",
        source_text=normalized,
        translated_text=translated,
        provider="cloudflare",
        model=os.environ.get("CLOUDFLARE_TRANSLATION_MODEL") or DEFAULT_MODEL,
    )
    return translated


def _text_hash(text: str, source_lang: str, target_lang: str) -> str:
    canonical = f"{source_lang}\n{target_lang}\n{text.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
