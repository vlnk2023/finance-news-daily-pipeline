from datetime import date

from scripts.generate_digest import _translated_coverage, build_digest


def test_build_digest_groups_items_and_outputs_markdown() -> None:
    digest = build_digest(
        date(2026, 5, 7),
        [
            {
                "title_zh": "中国央行连续第18个月增持黄金",
                "summary_zh": "央行公告显示黄金储备继续增加。",
                "url": "https://example.com/a",
            },
            {
                "title_zh": "恒指半日上涨",
                "summary_zh": "港股科技指数涨幅扩大。",
                "url": "https://example.com/b",
            },
        ],
    )

    assert digest["digest_date"] == "2026-05-07"
    assert "财经新闻日报" in digest["title"]
    assert "## 今日要点" in digest["markdown"]
    assert digest["json_summary"]["item_count"] == 2


def test_build_digest_candidate_mode_outputs_ranked_sections_and_metadata() -> None:
    digest = build_digest(
        date(2026, 5, 8),
        [
            {
                "guid": "g1",
                "title_zh": "美联储按兵不动",
                "summary_zh": "政策声明维持谨慎基调。",
                "translation_status": "translated",
                "_candidate_rank": 1,
                "_candidate_importance_score": 6.8,
                "_candidate_source_ids": ["a", "b"],
                "_candidate_cluster_id": "c1",
            },
            {
                "guid": "g2",
                "title_zh": "原油价格波动加剧",
                "summary_zh": "地缘风险与库存数据共同影响。",
                "translation_status": "pending",
                "_candidate_rank": 8,
                "_candidate_importance_score": 4.2,
                "_candidate_source_ids": ["a"],
                "_candidate_cluster_id": "c2",
            },
        ],
        use_candidates=True,
        candidate_coverage=0.5,
        candidate_count=2,
    )

    assert "候选池分层日报" in digest["markdown"]
    assert "## 今日头条" in digest["markdown"]
    assert "[#1|score=6.8|src=2]" in digest["markdown"]
    assert digest["json_summary"]["candidate_mode"] is True
    assert digest["json_summary"]["candidate_translated_coverage"] == 0.5
    assert len(digest["json_summary"]["top_clusters"]) == 2


def test_translated_coverage_calculation() -> None:
    coverage = _translated_coverage(
        [
            {"translation_status": "translated"},
            {"translation_status": "failed"},
            {"translation_status": "translated"},
        ]
    )
    assert coverage == 2 / 3
