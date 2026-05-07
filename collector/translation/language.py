"""Small dependency-free language heuristics for pipeline state routing."""

from __future__ import annotations

import re


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """Return a coarse BCP-47-ish language code for routing translation work."""
    normalized = (text or "").strip()
    if not normalized:
        return "unknown"

    cjk_count = len(CJK_RE.findall(normalized))
    latin_count = len(LATIN_RE.findall(normalized))
    if cjk_count >= 3 and cjk_count >= latin_count:
        return "zh-Hans"
    if HIRAGANA_KATAKANA_RE.search(normalized):
        return "ja"
    if HANGUL_RE.search(normalized):
        return "ko"
    if CYRILLIC_RE.search(normalized):
        return "ru"
    if latin_count:
        return "en"
    return "unknown"


def is_chinese(language: str) -> bool:
    return language.lower().startswith("zh")
