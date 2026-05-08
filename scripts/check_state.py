"""Diagnostic script to inspect current Supabase state."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collector.storage.supabase_store import SupabaseStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Supabase state and optionally enforce limits.")
    parser.add_argument("--max-pending", type=int, default=None)
    parser.add_argument("--max-failed", type=int, default=None)
    args = parser.parse_args()

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

    clusters = store.session.get(
        f"{store.url}/rest/v1/intelligence_clusters",
        params={"select": "id", "limit": "5000"},
        headers=store._headers(),
    ).json()
    candidates = store.session.get(
        f"{store.url}/rest/v1/digest_candidates",
        params={"select": "id", "limit": "5000"},
        headers=store._headers(),
    ).json()
    print(f"[STATE] intelligence_clusters={len(clusters)} digest_candidates={len(candidates)}")

    violations = []
    if args.max_pending is not None and pending > args.max_pending:
        violations.append(f"pending={pending} exceeds max_pending={args.max_pending}")
    if args.max_failed is not None and failed > args.max_failed:
        violations.append(f"failed={failed} exceeds max_failed={args.max_failed}")
    if violations:
        for violation in violations:
            print(f"[STATE][ERROR] {violation}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
