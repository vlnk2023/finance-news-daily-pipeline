import scripts.translate as translate_script
from collector.translation.third_party import ThirdPartyTranslator, parse_provider_list


class FakeStore:
    def __init__(self, cached=None):
        self.cached = cached
        self.upserted = []

    def fetch_translation(self, source_hash):
        return self.cached

    def upsert_translation(self, **fields):
        self.upserted.append(fields)


class FailingTranslator:
    def translate(self, text, *, source_lang, target_lang):
        raise RuntimeError("quota exceeded")


class FakeFallbackTranslator:
    def translate(self, text, *, source_lang, target_lang):
        return translate_script.TextTranslationOutcome(
            text=f"兜底翻译：{text}",
            provider="third-party",
            model="translators-bing",
        )


def test_parse_provider_list_uses_defaults_for_empty_value() -> None:
    assert parse_provider_list("") == (
        "deep-translator-google",
        "googletrans",
        "translators-bing",
        "translators-google",
    )


def test_third_party_translator_keeps_custom_provider_order() -> None:
    translator = ThirdPartyTranslator(["googletrans", "translators-bing"])

    assert translator.providers == ("googletrans", "translators-bing")


def test_translate_text_uses_cache_before_network_providers() -> None:
    store = FakeStore(
        {
            "translated_text": "缓存译文",
            "provider": "cloudflare",
            "model": "@cf/meta/m2m100-1.2b",
        }
    )
    stats = {"cache_hits": 0, "cloudflare_texts": 0, "fallback_texts": 0}

    outcome = translate_script._translate_text(
        store,
        FailingTranslator(),
        FakeFallbackTranslator(),
        "hello",
        source_lang="en",
        stats=stats,
    )

    assert outcome.text == "缓存译文"
    assert outcome.cache_hit is True
    assert stats["cache_hits"] == 1
    assert store.upserted == []


def test_translate_text_falls_back_when_cloudflare_fails() -> None:
    store = FakeStore()
    stats = {"cache_hits": 0, "cloudflare_texts": 0, "fallback_texts": 0}

    outcome = translate_script._translate_text(
        store,
        FailingTranslator(),
        FakeFallbackTranslator(),
        "market news",
        source_lang="en",
        stats=stats,
    )

    assert outcome.text == "兜底翻译：market news"
    assert outcome.provider == "third-party"
    assert outcome.model == "translators-bing"
    assert stats["fallback_texts"] == 1
    assert store.upserted[0]["provider"] == "third-party"
    assert store.upserted[0]["model"] == "translators-bing"
