from collector.translation.cloudflare import _extract_translation


def test_extracts_current_workers_ai_translation_shape() -> None:
    data = {
        "success": True,
        "result": {"translated_text": "你好"},
        "errors": [],
        "messages": [],
    }

    assert _extract_translation(data) == "你好"


def test_extracts_legacy_workers_ai_answer_shape() -> None:
    data = {
        "success": True,
        "result": {"answer": "你好"},
        "errors": [],
        "messages": [],
    }

    assert _extract_translation(data) == "你好"
