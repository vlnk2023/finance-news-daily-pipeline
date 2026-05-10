"""Assert full pipeline chain integrity for a given digest date."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_CHAIN_JOBS = [
    "collect",
    "audit_source_health",
    "build_clusters",
    "select_candidates",
    "translate",
    "validate_digest_inputs",
    "generate_digest",
]


@dataclass(frozen=True)
class IntegrityReport:
    digest_date: str
    missing_jobs: list[str]
    failed_jobs: list[str]
    mode_mismatches: list[str]
    selected_runs: dict[str, dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not self.missing_jobs and not self.failed_jobs and not self.mode_mismatches

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest_date": self.digest_date,
            "ok": self.ok,
            "missing_jobs": self.missing_jobs,
            "failed_jobs": self.failed_jobs,
            "mode_mismatches": self.mode_mismatches,
            "selected_runs": self.selected_runs,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert pipeline chain integrity by digest date.")
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument(
        "--lookback-runs",
        type=int,
        default=240,
        help="How many recent pipeline runs to inspect.",
    )
    parser.add_argument(
        "--require-validation-mode",
        choices=["any", "normal", "degraded", "blocked"],
        default="any",
        help="Expected digest gate mode for validate/generate stages.",
    )
    parser.add_argument(
        "--chain-jobs",
        nargs="+",
        default=DEFAULT_CHAIN_JOBS,
        help="Expected chain jobs in logical order.",
    )
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    store = SupabaseStore()
    rows = fetch_recent_pipeline_runs(store, limit=max(args.lookback_runs, 20))
    report = evaluate_chain_integrity(
        rows,
        digest_date=digest_date.isoformat(),
        chain_jobs=args.chain_jobs,
        required_validation_mode=args.require_validation_mode,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    if not report.ok:
        raise SystemExit(1)


def fetch_recent_pipeline_runs(store: SupabaseStore, *, limit: int) -> list[dict[str, Any]]:
    endpoint = f"{store.url}/rest/v1/pipeline_runs"
    response = store.session.get(
        endpoint,
        params={
            "select": "job_type,status,started_at,finished_at,error,stats,digest_date:stats->>digest_date",
            "order": "started_at.desc",
            "limit": str(limit),
        },
        headers=store._headers(),
        timeout=store.timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def evaluate_chain_integrity(
    rows: list[dict[str, Any]],
    *,
    digest_date: str,
    chain_jobs: list[str],
    required_validation_mode: str,
) -> IntegrityReport:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        job_type = str(row.get("job_type") or "")
        if job_type not in chain_jobs:
            continue
        row_date = extract_digest_date(row)
        if row_date != digest_date:
            continue
        if job_type in selected:
            continue
        selected[job_type] = row

    missing_jobs = [job for job in chain_jobs if job not in selected]
    failed_jobs = [
        job
        for job in chain_jobs
        if job in selected and str(selected[job].get("status") or "").lower() != "success"
    ]
    mode_mismatches = validate_gate_modes(
        selected,
        required_validation_mode=required_validation_mode,
    )

    selected_runs = {
        job: normalize_run_summary(selected[job])
        for job in chain_jobs
        if job in selected
    }
    return IntegrityReport(
        digest_date=digest_date,
        missing_jobs=missing_jobs,
        failed_jobs=failed_jobs,
        mode_mismatches=mode_mismatches,
        selected_runs=selected_runs,
    )


def extract_digest_date(row: dict[str, Any]) -> str:
    stats = normalize_stats(row.get("stats"))
    direct = str(row.get("digest_date") or "").strip()
    if direct:
        return direct
    return str(stats.get("digest_date") or "").strip()


def normalize_stats(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def normalize_run_summary(row: dict[str, Any]) -> dict[str, Any]:
    stats = normalize_stats(row.get("stats"))
    mode = str(stats.get("digest_mode") or stats.get("validation_mode") or "").strip()
    return {
        "status": str(row.get("status") or ""),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "mode": mode,
        "error": row.get("error"),
    }


def validate_gate_modes(
    selected_runs: dict[str, dict[str, Any]],
    *,
    required_validation_mode: str,
) -> list[str]:
    if required_validation_mode == "any":
        return []

    mismatches: list[str] = []
    validate_row = selected_runs.get("validate_digest_inputs")
    if validate_row:
        validate_mode = extract_mode(validate_row)
        if validate_mode and validate_mode != required_validation_mode:
            mismatches.append(
                "validate_digest_inputs mode mismatch: "
                f"expected={required_validation_mode} got={validate_mode}"
            )

    generate_row = selected_runs.get("generate_digest")
    if generate_row:
        generate_mode = extract_mode(generate_row)
        if generate_mode and generate_mode != required_validation_mode:
            mismatches.append(
                "generate_digest mode mismatch: "
                f"expected={required_validation_mode} got={generate_mode}"
            )
    return mismatches


def extract_mode(row: dict[str, Any]) -> str:
    stats = normalize_stats(row.get("stats"))
    return str(stats.get("digest_mode") or stats.get("validation_mode") or "").strip()


if __name__ == "__main__":
    main()
