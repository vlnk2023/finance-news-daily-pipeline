"""Select top-ranked clusters as digest candidates for a given day."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore

DEFAULT_TIMEZONE = "Asia/Shanghai"


def main() -> None:
    parser = argparse.ArgumentParser(description="Select digest candidates from clusters.")
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--max-candidates", type=int, default=40)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()

    store = SupabaseStore()
    clusters = store.fetch_clusters_for_date(digest_date=digest_date.isoformat(), limit=args.limit)
    candidates = select_candidates(digest_date=digest_date, clusters=clusters, max_candidates=args.max_candidates)
    store.replace_digest_candidates_for_date(
        digest_date=digest_date.isoformat(),
        candidates=candidates,
    )
    print(
        json.dumps(
            {
                "digest_date": digest_date.isoformat(),
                "clusters": len(clusters),
                "candidates": len(candidates),
            },
            ensure_ascii=False,
        )
    )


def select_candidates(
    *,
    digest_date: date,
    clusters: list[dict[str, object]],
    max_candidates: int,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    sorted_clusters = sorted(
        clusters,
        key=lambda row: (
            float(row.get("importance_score") or 0),
            int(row.get("item_count") or 0),
        ),
        reverse=True,
    )
    for rank, cluster in enumerate(sorted_clusters[: max(max_candidates, 0)], start=1):
        selected.append(
            {
                "digest_date": digest_date.isoformat(),
                "cluster_id": cluster.get("id"),
                "representative_item_guid": cluster.get("representative_item_guid"),
                "rank": rank,
                "importance_score": cluster.get("importance_score") or 0,
                "source_ids": cluster.get("source_ids") or [],
                "status": "selected",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return selected


if __name__ == "__main__":
    main()
