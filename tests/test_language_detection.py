from collector.translation import detect_language, is_chinese


def test_detects_chinese_text() -> None:
    language = detect_language("中国央行连续第18个月增持黄金")

    assert language == "zh-Hans"
    assert is_chinese(language)


def test_detects_latin_text_as_english_route() -> None:
    language = detect_language("Federal Reserve officials discuss inflation outlook")

    assert language == "en"
    assert not is_chinese(language)
