"""HTTP fetcher for Telegram public static pages."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Mapping

import requests

from collector.rate_limiter import InProcessRateLimiter, RateLimiter


LOGGER = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/124 Safari/537.36"
    )
}


@dataclass(frozen=True)
class FetchResult:
    """Fetched HTML plus request metadata."""

    url: str
    html: str
    status_code: int
    elapsed_ms: int
    attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "elapsed_ms": self.elapsed_ms,
            "attempts": self.attempts,
        }


class TelegramFetcher:
    """Fetch Telegram static pages with retry and simple in-process rate limit."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        headers: Mapping[str, str] | None = None,
        retry_base_delay_seconds: float = 1.0,
        retry_max_delay_seconds: float = 30.0,
        min_interval_seconds: float = 1.0,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.headers = dict(DEFAULT_HEADERS)
        if headers:
            self.headers.update(headers)
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
        self.rate_limiter = rate_limiter or InProcessRateLimiter(min_interval_seconds)

    def fetch(
        self,
        url: str,
        *,
        timeout_ms: int = 12000,
        retries: int = 2,
    ) -> FetchResult:
        timeout_seconds = max(timeout_ms / 1000, 0.1)
        attempts = max(retries, 0) + 1
        started_at = time.monotonic()
        last_error: BaseException | None = None

        for attempt in range(1, attempts + 1):
            self.rate_limiter.wait()
            try:
                response = self.session.get(
                    url,
                    headers=self.headers,
                    timeout=timeout_seconds,
                )
                status_code = response.status_code
                if status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                    LOGGER.warning(
                        "retryable Telegram response url=%s status=%s attempt=%s",
                        url,
                        status_code,
                        attempt,
                    )
                    self._sleep_before_retry(attempt)
                    continue

                response.raise_for_status()
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                return FetchResult(
                    url=url,
                    html=response.text,
                    status_code=status_code,
                    elapsed_ms=elapsed_ms,
                    attempts=attempt,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                LOGGER.warning(
                    "Telegram fetch failed url=%s attempt=%s error=%s",
                    url,
                    attempt,
                    exc,
                )
                self._sleep_before_retry(attempt)

        raise RuntimeError(f"failed to fetch Telegram page after {attempts} attempts: {url}") from last_error

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(
            self.retry_base_delay_seconds * (2 ** (attempt - 1)),
            self.retry_max_delay_seconds,
        )
        jitter = random.uniform(0, min(delay * 0.2, 1.0))
        time.sleep(delay + jitter)
