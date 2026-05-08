from datetime import date

from scripts.build_clusters import build_clusters_for_date
from scripts.select_digest_candidates import select_candidates


def test_build_clusters_groups_items_by_canonical_external_url() -> None:
    digest_date = date(2026, 5, 8)
    items = [
        {
            "guid": "a1",
            "source_id": "tg_bloomberg",
            "source_lang": "en",
            "title": "Fed keeps rates unchanged",
            "summary": "Update one",
            "url": "https://t.me/bloomberg/1",
            "external_url": "https://example.com/news?id=1&utm_source=tg",
            "published_at": "2026-05-08T00:01:00+00:00",
        },
        {
            "guid": "a2",
            "source_id": "tg_bloombergs",
            "source_lang": "en",
            "title": "Fed keeps rates unchanged",
            "summary": "Update two",
            "url": "https://t.me/bloombergs/2",
            "external_url": "https://example.com/news?id=1",
            "published_at": "2026-05-08T00:02:00+00:00",
        },
        {
            "guid": "b1",
            "source_id": "tg_quanxiaowa",
            "source_lang": "zh",
            "title": "央行持续增持黄金",
            "summary": "黄金储备更新",
            "url": "https://t.me/quanxiaowa/8",
            "external_url": "",
            "published_at": "2026-05-08T01:00:00+00:00",
        },
    ]

    clusters, members = build_clusters_for_date(digest_date, items)

    assert len(clusters) == 2
    assert len(members) == 3
    top = clusters[0]
    assert top["item_count"] == 2
    assert "example.com/news?id=1" in str(top["canonical_url"])


def test_select_candidates_ranks_by_importance_and_size() -> None:
    digest_date = date(2026, 5, 8)
    clusters = [
        {
            "id": "c1",
            "representative_item_guid": "g1",
            "importance_score": 6.0,
            "item_count": 4,
            "source_ids": ["a", "b"],
        },
        {
            "id": "c2",
            "representative_item_guid": "g2",
            "importance_score": 5.5,
            "item_count": 8,
            "source_ids": ["a"],
        },
    ]

    candidates = select_candidates(digest_date=digest_date, clusters=clusters, max_candidates=1)

    assert len(candidates) == 1
    assert candidates[0]["cluster_id"] == "c1"
    assert candidates[0]["rank"] == 1
