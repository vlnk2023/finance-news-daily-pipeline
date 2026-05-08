"""Translate pending news items and update normalized Chinese fields."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore
from collector.translation import detect_language, is_chinese
from collector.translation.cloudflare import (
    DEFAULT_MODEL,
    CloudflareTranslator,
)
from collector.translation.third_party import ThirdPartyTranslator, parse_provider_list
from scripts.pipeline_run_tracker import track_pipeline_run


TARGET_LANG = "zh"
DEFAULT_TIMEZONE = "Asia/Shanghai"


@dataclass(frozen=True)
class TextTranslationOutcome:
    text: str
    provider: str
    model: str
    cache_hit: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending news item translations.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--provider",
        choices=["cloudflare", "state-only"],
        default=os.environ.get("TRANSLATION_PROVIDER", "cloudflare"),
    )
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help="Translate only representative news items selected in digest_candidates.",
    )
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD for candidate-only mode.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--candidate-limit", type=int, default=40)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Include failed status when fetching candidate-only translation tasks.",
    )
    parser.add_argument(
        "--fallback-providers",
        default=os.environ.get("TRANSLATION_FALLBACK_PROVIDERS", ""),
        help=(
            "Comma-separated no-key fallback providers. "
            "Default: deep-translator-google,googletrans,translators-bing,translators-google."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    with track_pipeline_run(
        "translate",
        initial_stats={
            "provider": args.provider,
            "candidate_only": bool(args.candidate_only),
            "candidate_limit": args.candidate_limit,
            "retry_failed": bool(args.retry_failed),
        },
    ) as run_stats:
        store = SupabaseStore()
        translator = None
        fallback_translator = None
        if args.provider == "cloudflare":
            try:
                translator = CloudflareTranslator()
                print("[TRANSLATE] CloudflareTranslator initialized OK")
            except Exception as exc:
                print(f"[TRANSLATE] CloudflareTranslator init FAILED: {exc}")
                logging.error("CloudflareTranslator init failed: %s", exc)
            fallback_translator = ThirdPartyTranslator(parse_provider_list(args.fallback_providers))
            print(f"[TRANSLATE] fallback providers={','.join(fallback_translator.providers)}")
            run_stats["fallback_providers"] = ",".join(fallback_translator.providers)

        items: list[dict[str, str]]
        if args.candidate_only:
            tz = ZoneInfo(args.timezone)
            digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
            statuses = ("pending", "failed") if args.retry_failed else ("pending",)
            items = store.fetch_candidate_translation_items(
                digest_date=digest_date.isoformat(),
                limit=args.candidate_limit,
                statuses=statuses,
            )
            run_stats["digest_date"] = digest_date.isoformat()
            run_stats["candidate_statuses"] = ",".join(statuses)
            print(
                "[TRANSLATE] candidate-only mode "
                f"date={digest_date.isoformat()} limit={args.candidate_limit} statuses={','.join(statuses)}"
            )
        else:
            items = store.fetch_pending_translation_items(limit=args.limit)

        print(f"[TRANSLATE] fetched {len(items)} translation tasks from Supabase")
        stats = {
            "fetched": len(items),
            "zh_completed": 0,
            "cache_hits": 0,
            "cloudflare_texts": 0,
            "fallback_texts": 0,
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
                if translator is None and fallback_translator is None:
                    stats["pending_external"] += 1
                else:
                    try:
                        title_outcome = _translate_text(
                            store,
                            translator,
                            fallback_translator,
                            item.get("title") or "",
                            source_lang=source_lang,
                            stats=stats,
                        )
                        summary_outcome = _translate_text(
                            store,
                            translator,
                            fallback_translator,
                            item.get("summary") or "",
                            source_lang=source_lang,
                            stats=stats,
                        )
                        fields.update(
                            {
                                "title_zh": title_outcome.text,
                                "summary_zh": summary_outcome.text,
                                "translation_status": "translated",
                            }
                        )
                    except Exception as exc:
                        logging.exception("translation failed guid=%s", item.get("guid"))
                        fields.update(
                            {
                                "translation_status": "failed",
                            }
                        )
                        stats["failed"] += 1

            store.update_news_item(item["id"], fields)

        run_stats.update(stats)
        print(
            f"[TRANSLATE] done fetched={stats['fetched']} zh_completed={stats['zh_completed']} "
            f"cloudflare_texts={stats['cloudflare_texts']} fallback_texts={stats['fallback_texts']} "
            f"cache_hits={stats['cache_hits']} "
            f"failed={stats['failed']} pending_external={stats['pending_external']}"
        )
        logging.info(
            (
                "translation processed fetched=%s zh_completed=%s cache_hits=%s "
                "cloudflare_texts=%s fallback_texts=%s pending_external=%s failed=%s"
            ),
            stats["fetched"],
            stats["zh_completed"],
            stats["cache_hits"],
            stats["cloudflare_texts"],
            stats["fallback_texts"],
            stats["pending_external"],
            stats["failed"],
        )


def _translate_text(
    store: SupabaseStore,
    translator: CloudflareTranslator | None,
    fallback_translator: ThirdPartyTranslator | None,
    text: str,
    *,
    source_lang: str,
    stats: dict[str, int],
) -> TextTranslationOutcome:
    normalized = (text or "").strip()
    if not normalized:
        return TextTranslationOutcome(text="", provider="empty", model="empty")

    source_hash = _text_hash(normalized, source_lang, TARGET_LANG)
    cached = store.fetch_translation(source_hash)
    if cached:
        stats["cache_hits"] += 1
        return TextTranslationOutcome(
            text=cached["translated_text"],
            provider=cached.get("provider") or "cache",
            model=cached.get("model") or "cache",
            cache_hit=True,
        )

    errors: list[str] = []
    translated = ""
    provider = ""
    model = ""

    if translator is not None:
        try:
            translated = translator.translate(
                normalized,
                source_lang=source_lang,
                target_lang=TARGET_LANG,
            )
            provider = "cloudflare"
            model = os.environ.get("CLOUDFLARE_TRANSLATION_MODEL") or DEFAULT_MODEL
            stats["cloudflare_texts"] += 1
        except Exception as exc:
            errors.append(f"cloudflare: {exc}")
            logging.warning("Cloudflare translation failed; trying fallback: %s", exc)

    if not translated and fallback_translator is not None:
        result = fallback_translator.translate(
            normalized,
            source_lang=source_lang,
            target_lang=TARGET_LANG,
        )
        translated = result.text
        provider = result.provider
        model = result.model
        stats["fallback_texts"] += 1

    if not translated:
        raise RuntimeError("; ".join(errors) or "translation returned empty response")

    store.upsert_translation(
        source_hash=source_hash,
        source_lang=source_lang,
        target_lang="zh-Hans",
        source_text=normalized,
        translated_text=translated,
        provider=provider,
        model=model,
    )
    return TextTranslationOutcome(text=translated, provider=provider, model=model)


def _text_hash(text: str, source_lang: str, target_lang: str) -> str:
    canonical = f"{source_lang}\n{target_lang}\n{text.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
