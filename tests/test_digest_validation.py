from scripts.validate_digest_inputs import validate_items


def test_validate_items_returns_normal_for_healthy_candidate_pool() -> None:
    items = [
        {"translation_status": "translated", "_candidate_rank": 1},
        {"translation_status": "translated", "_candidate_rank": 2},
        {"translation_status": "translated", "_candidate_rank": 3},
        {"translation_status": "translated", "_candidate_rank": 4},
        {"translation_status": "translated", "_candidate_rank": 5},
        {"translation_status": "translated", "_candidate_rank": 6},
        {"translation_status": "translated", "_candidate_rank": 7},
        {"translation_status": "pending", "_candidate_rank": 8},
        {"translation_status": "pending", "_candidate_rank": 9},
        {"translation_status": "pending", "_candidate_rank": 10},
    ]
    result = validate_items(
        items,
        min_candidates=10,
        min_translated_candidates=7,
        min_coverage=0.7,
        top_window=5,
        min_top_translated=4,
        mode_on_fail="degraded",
    )

    assert result.mode == "normal"
    assert result.reason == ""
    assert result.candidate_count == 10
    assert result.translated_count == 7


def test_validate_items_returns_degraded_with_reasons_on_failure() -> None:
    items = [
        {"translation_status": "translated", "_candidate_rank": 1},
        {"translation_status": "pending", "_candidate_rank": 2},
        {"translation_status": "pending", "_candidate_rank": 3},
    ]
    result = validate_items(
        items,
        min_candidates=10,
        min_translated_candidates=7,
        min_coverage=0.7,
        top_window=5,
        min_top_translated=4,
        mode_on_fail="degraded",
    )

    assert result.mode == "degraded"
    assert "candidate_count=3 < min_candidates=10" in result.reason
    assert "translated_candidate_count=1 < min_translated_candidates=7" in result.reason
