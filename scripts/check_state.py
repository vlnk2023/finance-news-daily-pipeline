"""Diagnostic script to inspect current Supabase state."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collector.storage.supabase_store import SupabaseStore


def main() -> None:
    store = SupabaseStore()

    sources = store.session.get(
        f"{store.url}/rest/v1/sources",
        params={"select": "id", "order": "id"},
        headers=store._headers(),
    ).json()
    print(f"[STATE] sources={len(sources)}")

    item_counts = store.session.get(
        f"{store.url}/rest/v1/news_items",
        params={"select": "translation_status"},
        headers=store._headers(),
    ).json()
    total_items = len(item_counts)
    pending = sum(1 for item in item_counts if item.get("translation_status") == "pending")
    translated = sum(1 for item in item_counts if item.get("translation_status") == "translated")
    failed = sum(1 for item in item_counts if item.get("translation_status") == "failed")
    print(f"[STATE] news_items total={total_items} pending={pending} translated={translated} failed={failed}")

    digests = store.session.get(
        f"{store.url}/rest/v1/daily_digests",
        params={"select": "digest_date,model,generated_at", "order": "digest_date.desc", "limit": "5"},
        headers=store._headers(),
    ).json()
    print(f"[STATE] daily_digests={len(digests)}")
    for digest in digests:
        print(f"[STATE]   {digest['digest_date']} model={digest.get('model','?')} generated={digest.get('generated_at','?')}")


if __name__ == "__main__":
    main()
