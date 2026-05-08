"""Best-effort no-key translation fallbacks.

These providers use unofficial or public web translation paths. They are useful
as a final safety net, but Cloudflare/Azure-style official APIs should remain
the primary translation route.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Callable


DEFAULT_FALLBACK_PROVIDERS = (
    "deep-translator-google",
    "googletrans",
    "translators-bing",
    "translators-google",
)


class ThirdPartyTranslationError(RuntimeError):
    """Raised when every third-party fallback translator fails."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    provider: str
    model: str


class ThirdPartyTranslator:
    """Try no-key translators in a deterministic fallback order."""

    def __init__(self, providers: list[str] | tuple[str, ...] | None = None) -> None:
        self.providers = tuple(providers or DEFAULT_FALLBACK_PROVIDERS)

    def translate(self, text: str, *, source_lang: str, target_lang: str = "zh") -> TranslationResult:
        normalized = (text or "").strip()
        if not normalized:
            return TranslationResult(text="", provider="third-party", model="empty")

        errors: list[str] = []
        for provider in self.providers:
            try:
                translated = _provider_call(provider, normalized, source_lang, target_lang)
            except Exception as exc:
                errors.append(f"{provider}: {exc}")
                continue
            translated = (translated or "").strip()
            if translated:
                return TranslationResult(
                    text=translated,
                    provider="third-party",
                    model=provider,
                )
            errors.append(f"{provider}: empty response")

        raise ThirdPartyTranslationError("; ".join(errors))


def parse_provider_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_FALLBACK_PROVIDERS
    providers = tuple(part.strip() for part in value.split(",") if part.strip())
    return providers or DEFAULT_FALLBACK_PROVIDERS


def _provider_call(provider: str, text: str, source_lang: str, target_lang: str) -> str:
    handlers: dict[str, Callable[[str, str, str], str]] = {
        "deep-translator-google": _deep_translator_google,
        "googletrans": _googletrans,
        "translators-bing": lambda q, src, dst: _translators(q, src, dst, translator="bing"),
        "translators-google": lambda q, src, dst: _translators(q, src, dst, translator="google"),
    }
    if provider not in handlers:
        raise ThirdPartyTranslationError(f"unknown fallback provider: {provider}")
    return handlers[provider](text, source_lang, target_lang)


def _deep_translator_google(text: str, source_lang: str, target_lang: str) -> str:
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(
        source=_web_source_lang(source_lang),
        target=_web_target_lang(target_lang),
    )
    return translator.translate(text=text)


def _googletrans(text: str, source_lang: str, target_lang: str) -> str:
    try:
        return _run_async(_googletrans_async(text, source_lang, target_lang))
    except TypeError:
        return _googletrans_sync(text, source_lang, target_lang)


async def _googletrans_async(text: str, source_lang: str, target_lang: str) -> str:
    from googletrans import Translator

    try:
        translator = Translator(service_urls=["translate.googleapis.com"])
    except TypeError:
        translator = Translator()

    if hasattr(translator, "__aenter__"):
        async with translator as active_translator:
            result = await active_translator.translate(
                text,
                src=_googletrans_source_lang(source_lang),
                dest=_googletrans_target_lang(target_lang),
            )
    else:
        result = translator.translate(
            text,
            src=_googletrans_source_lang(source_lang),
            dest=_googletrans_target_lang(target_lang),
        )
        if inspect.isawaitable(result):
            result = await result

    return _translation_text(result)


def _googletrans_sync(text: str, source_lang: str, target_lang: str) -> str:
    from googletrans import Translator

    try:
        translator = Translator(service_urls=["translate.googleapis.com"])
    except TypeError:
        translator = Translator()
    result = translator.translate(
        text,
        src=_googletrans_source_lang(source_lang),
        dest=_googletrans_target_lang(target_lang),
    )
    return _translation_text(result)


def _translators(text: str, source_lang: str, target_lang: str, *, translator: str) -> str:
    import translators as ts

    return ts.translate_text(
        text,
        translator=translator,
        from_language=_translators_source_lang(source_lang),
        to_language=_translators_target_lang(target_lang),
        timeout=20,
        if_print_warning=False,
    )


def _run_async(coro: object) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise ThirdPartyTranslationError("googletrans async fallback cannot run inside an active event loop")


def _translation_text(result: object) -> str:
    value = getattr(result, "text", result)
    return str(value or "")


def _web_source_lang(language: str) -> str:
    language = (language or "").strip()
    return "auto" if language in {"", "unknown"} else language


def _web_target_lang(language: str) -> str:
    if language in {"zh", "zh-Hans", "zh-cn", "zh-CN"}:
        return "zh-CN"
    return language or "zh-CN"


def _googletrans_source_lang(language: str) -> str:
    language = _web_source_lang(language)
    return "auto" if language == "unknown" else language


def _googletrans_target_lang(language: str) -> str:
    if language in {"zh", "zh-Hans", "zh-CN"}:
        return "zh-cn"
    return language or "zh-cn"


def _translators_source_lang(language: str) -> str:
    return _web_source_lang(language)


def _translators_target_lang(language: str) -> str:
    if language in {"zh", "zh-Hans", "zh-CN", "zh-cn"}:
        return "zh"
    return language or "zh"
