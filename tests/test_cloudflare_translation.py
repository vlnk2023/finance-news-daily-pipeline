from collector.translation.cloudflare import _extract_generation, _extract_translation


def test_extracts_current_workers_ai_translation_shape() -> None:
    data = {
        "success": True,
        "result": {"translated_text": "hello"},
        "errors": [],
        "messages": [],
    }

    assert _extract_translation(data) == "hello"


def test_extracts_legacy_workers_ai_answer_shape() -> None:
    data = {
        "success": True,
        "result": {"answer": "hello"},
        "errors": [],
        "messages": [],
    }

    assert _extract_translation(data) == "hello"


def test_extracts_workers_ai_generation_shape() -> None:
    data = {
        "success": True,
        "result": {"response": "digest content"},
        "errors": [],
        "messages": [],
    }

    assert _extract_generation(data) == "digest content"


def test_extracts_empty_translated_text_without_error() -> None:
    data = {
        "success": True,
        "result": {"translated_text": ""},
        "errors": [],
        "messages": [],
    }

    assert _extract_translation(data) == ""
