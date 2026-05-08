"""Build same-day intelligence clusters from collected news items."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore

DEFAULT_TIMEZONE = "Asia/Shanghai"
TITLE_TOKEN_RE = re.compile(r"[\W_]+", re.UNICODE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily intelligence clusters.")
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    start_at, end_at = _utc_bounds(digest_date, tz)

    store = SupabaseStore()
    items = store.fetch_news_items_for_window(
        start_at=start_at.isoformat(),
        end_at=end_at.isoformat(),
        limit=args.limit,
    )
    clusters, members = build_clusters_for_date(digest_date, items)
    store.replace_clusters_for_date(
        digest_date=digest_date.isoformat(),
        clusters=clusters,
        members=members,
    )
    print(
        json.dumps(
            {
                "digest_date": digest_date.isoformat(),
                "items": len(items),
                "clusters": len(clusters),
                "members": len(members),
            },
            ensure_ascii=False,
        )
    )


def build_clusters_for_date(
    digest_date: date,
    items: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    reasons: dict[str, str] = {}
    for item in items:
        cluster_key, reason = _cluster_key(item)
        grouped[cluster_key].append(item)
        reasons.setdefault(cluster_key, reason)

    clusters: list[dict[str, object]] = []
    members: list[dict[str, object]] = []
    for cluster_key, group_items in grouped.items():
        representative = _representative(group_items)
        cluster_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{digest_date.isoformat()}:{cluster_key}"))
        source_ids = sorted({(row.get("source_id") or "") for row in group_items if row.get("source_id")})
        language_mix = Counter((row.get("source_lang") or "unknown") for row in group_items)
        importance_score = _importance_score(group_items, source_ids)
        clusters.append(
            {
                "id": cluster_id,
                "digest_date": digest_date.isoformat(),
                "cluster_key": cluster_key,
                "representative_item_guid": representative.get("guid") or "",
                "canonical_title": representative.get("title") or "",
                "canonical_url": _canonical_url(representative.get("external_url") or representative.get("url") or ""),
                "source_ids": source_ids,
                "item_count": len(group_items),
                "language_mix": dict(language_mix),
                "importance_score": importance_score,
                "status": "built",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        for row in group_items:
            guid = row.get("guid") or ""
            if not guid:
                continue
            members.append(
                {
                    "cluster_id": cluster_id,
                    "digest_date": digest_date.isoformat(),
                    "news_item_guid": guid,
                    "source_id": row.get("source_id") or "",
                    "similarity_reason": reasons[cluster_key],
                }
            )

    clusters.sort(key=lambda row: (float(row["importance_score"]), int(row["item_count"])), reverse=True)
    return clusters, members


def _cluster_key(item: dict[str, str]) -> tuple[str, str]:
    canonical_external = _canonical_url(item.get("external_url") or "")
    if canonical_external:
        return f"url:{canonical_external}", "external_url"

    canonical_msg = _canonical_url(item.get("url") or "")
    if canonical_msg:
        return f"message:{canonical_msg}", "message_url"

    normalized_title = _normalize_title(item.get("title") or "")
    if normalized_title:
        title_hash = hashlib.sha1(normalized_title.encode("utf-8")).hexdigest()
        return f"title:{title_hash}", "normalized_title"

    content_hash = item.get("content_hash") or ""
    if content_hash:
        return f"content:{content_hash}", "content_hash"
    guid = item.get("guid") or ""
    return f"guid:{guid}", "guid"


def _canonical_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    netloc = parsed.netloc.lower()
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    filtered_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if not k.lower().startswith("utm_")]
    query = urlencode(filtered_query, doseq=True)
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def _normalize_title(title: str) -> str:
    lowered = (title or "").strip().lower()
    if not lowered:
        return ""
    tokens = [token for token in TITLE_TOKEN_RE.split(lowered) if token]
    return " ".join(tokens[:24])


def _representative(group_items: list[dict[str, str]]) -> dict[str, str]:
    def sort_key(row: dict[str, str]) -> tuple[int, str]:
        title = row.get("title") or ""
        published = row.get("published_at") or ""
        return (len(title), published)

    return sorted(group_items, key=sort_key, reverse=True)[0]


def _importance_score(group_items: list[dict[str, str]], source_ids: list[str]) -> float:
    item_count = len(group_items)
    source_count = len(source_ids)
    diversity_bonus = min(source_count, 5) * 0.6
    size_score = math.log2(item_count + 1.0) * 1.8
    return round(size_score + diversity_bonus, 4)


def _utc_bounds(digest_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = datetime.combine(digest_date, time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
