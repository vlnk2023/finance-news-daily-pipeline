"""Lightweight in-process rate limit helpers."""

from __future__ import annotations

import threading
import time
from typing import Protocol


class RateLimiter(Protocol):
    """Rate limiter protocol used by fetchers."""

    def wait(self) -> None:
        """Block until a request is allowed."""


class InProcessRateLimiter:
    """Thread-safe minimum-interval rate limiter.

    This is intentionally small: it keeps one timestamp in memory and works for
    a single Python process. Storage-backed distributed limits can implement the
    same `wait()` protocol later.
    """

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        *,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            elapsed = now - self._last_request_at
            wait_seconds = self.min_interval_seconds - elapsed
            if wait_seconds > 0:
                self._sleeper(wait_seconds)
                now = self._clock()
            self._last_request_at = now

