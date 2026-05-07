"""Cloudflare Workers AI translation provider."""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_MODEL = "@cf/meta/m2m100-1.2b"
DEFAULT_TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct-fp8-fast"
LANGUAGE_MAP = {
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "ru": "ru",
    "zh-Hans": "zh",
    "zh": "zh",
    "unknown": "en",
}


class CloudflareTranslationError(RuntimeError):
    """Raised when Cloudflare translation cannot be completed."""


class CloudflareGenerationError(RuntimeError):
    """Raised when Cloudflare text generation cannot be completed."""


class CloudflareTranslator:
    """Translate text through Cloudflare Workers AI."""

    def __init__(
        self,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self.model = model or os.environ.get("CLOUDFLARE_TRANSLATION_MODEL") or DEFAULT_MODEL
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        if not self.account_id or not self.api_token:
            raise CloudflareTranslationError(
                "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set."
            )

    def translate(self, text: str, *, source_lang: str, target_lang: str = "zh") -> str:
        normalized = (text or "").strip()
        if not normalized:
            return ""

        endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/ai/run/{self.model}"
        )
        response = self.session.post(
            endpoint,
            headers={"authorization": f"Bearer {self.api_token}"},
            json={
                "text": normalized,
                "source_lang": _cloudflare_lang(source_lang),
                "target_lang": target_lang,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", True):
            raise CloudflareTranslationError(str(data.get("errors") or data))
        return _extract_translation(data)


class CloudflareTextGenerator:
    """Generate text through Cloudflare Workers AI."""

    def __init__(
        self,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 90,
        session: requests.Session | None = None,
    ) -> None:
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self.model = model or os.environ.get("CLOUDFLARE_DIGEST_MODEL") or DEFAULT_TEXT_MODEL
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        if not self.account_id or not self.api_token:
            raise CloudflareGenerationError(
                "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set."
            )

    def generate(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int = 1600,
        temperature: float = 0.2,
    ) -> str:
        endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/ai/run/{self.model}"
        )
        response = self.session.post(
            endpoint,
            headers={"authorization": f"Bearer {self.api_token}"},
            json={
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", True):
            raise CloudflareGenerationError(str(data.get("errors") or data))
        return _extract_generation(data)


def _cloudflare_lang(language: str) -> str:
    return LANGUAGE_MAP.get(language, language or "en")


def _extract_translation(data: dict[str, Any]) -> str:
    result = data.get("result")
    if isinstance(result, dict):
        value = result.get("translated_text") or result.get("answer")
        if isinstance(value, str):
            return value
    if isinstance(result, str):
        return result
    value = data.get("translated_text") or data.get("answer")
    if isinstance(value, str):
        return value
    raise CloudflareTranslationError(f"Cloudflare response missing translated text: {data}")


def _extract_generation(data: dict[str, Any]) -> str:
    result = data.get("result")
    if isinstance(result, dict):
        value = result.get("response") or result.get("answer")
        if isinstance(value, str):
            return value
    if isinstance(result, str):
        return result
    value = data.get("response") or data.get("answer")
    if isinstance(value, str):
        return value
    raise CloudflareGenerationError(f"Cloudflare response missing generated text: {data}")
