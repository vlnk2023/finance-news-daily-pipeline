"""Best-effort pipeline run tracker persisted to Supabase."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from collector.storage.supabase_store import SupabaseConfigError, SupabaseStore

LOGGER = logging.getLogger(__name__)


@contextmanager
def track_pipeline_run(job_type: str, *, initial_stats: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    stats: dict[str, Any] = dict(initial_stats or {})
    started = time.monotonic()
    store = None
    run_id = None
    try:
        store = SupabaseStore()
        run_id = store.create_pipeline_run(job_type=job_type, stats=stats)
    except SupabaseConfigError:
        LOGGER.debug("pipeline run tracking disabled: missing Supabase config")
    except Exception as exc:  # pragma: no cover - best effort telemetry
        LOGGER.warning("pipeline run start failed job_type=%s error=%s", job_type, exc)

    try:
        yield stats
    except Exception as exc:
        stats["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        if store and run_id:
            try:
                store.finish_pipeline_run(
                    run_id,
                    status="failed",
                    stats=stats,
                    error=str(exc),
                )
            except Exception as finish_exc:  # pragma: no cover - best effort telemetry
                LOGGER.warning(
                    "pipeline run finish failed job_type=%s run_id=%s error=%s",
                    job_type,
                    run_id,
                    finish_exc,
                )
        raise
    else:
        stats["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        if store and run_id:
            try:
                store.finish_pipeline_run(run_id, status="success", stats=stats)
            except Exception as finish_exc:  # pragma: no cover - best effort telemetry
                LOGGER.warning(
                    "pipeline run finish failed job_type=%s run_id=%s error=%s",
                    job_type,
                    run_id,
                    finish_exc,
                )
