from datetime import date

from scripts.generate_digest import build_digest


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
