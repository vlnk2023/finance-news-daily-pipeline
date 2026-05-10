"""Validate candidate translation readiness before digest generation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from collector.storage.supabase_store import SupabaseStore
from scripts.pipeline_run_tracker import track_pipeline_run


DEFAULT_TIMEZONE = "Asia/Shanghai"


@dataclass(frozen=True)
class ValidationResult:
    mode: str
    reason: str
    candidate_count: int
    translated_count: int
    translated_top_count: int
    coverage: float

    def to_stats(self) -> dict[str, object]:
        return {
            "digest_mode": self.mode,
            "validation_reason": self.reason,
            "candidate_count": self.candidate_count,
            "translated_candidate_count": self.translated_count,
            "translated_top_candidate_count": self.translated_top_count,
            "candidate_coverage": self.coverage,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate digest candidate translation readiness.")
    parser.add_argument("--date", help="Digest date in YYYY-MM-DD. Defaults to local today.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--min-candidates", type=int, default=10)
    parser.add_argument("--min-translated-candidates", type=int, default=7)
    parser.add_argument("--min-coverage", type=float, default=0.7)
    parser.add_argument("--top-window", type=int, default=5)
    parser.add_argument("--min-top-translated", type=int, default=4)
    parser.add_argument(
        "--mode-on-fail",
        choices=["degraded", "blocked"],
        default="degraded",
        help="Digest mode used when validation fails.",
    )
    parser.add_argument(
        "--write-github-env",
        help="Optional path to append GitHub Actions environment variables.",
    )
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    digest_date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()

    with track_pipeline_run(
        "validate_digest_inputs",
        initial_stats={
            "digest_date": digest_date.isoformat(),
            "limit": args.limit,
            "min_candidates": args.min_candidates,
            "min_translated_candidates": args.min_translated_candidates,
            "min_coverage": args.min_coverage,
            "top_window": args.top_window,
            "min_top_translated": args.min_top_translated,
            "mode_on_fail": args.mode_on_fail,
        },
    ) as run_stats:
        store = SupabaseStore()
        items = store.fetch_digest_candidate_items(
            digest_date=digest_date.isoformat(),
            limit=args.limit,
        )
        result = validate_items(
            items,
            min_candidates=max(args.min_candidates, 0),
            min_translated_candidates=max(args.min_translated_candidates, 0),
            min_coverage=max(min(args.min_coverage, 1.0), 0.0),
            top_window=max(args.top_window, 0),
            min_top_translated=max(args.min_top_translated, 0),
            mode_on_fail=args.mode_on_fail,
        )
        run_stats.update(result.to_stats())
        run_stats["digest_date"] = digest_date.isoformat()

        if args.write_github_env:
            write_github_env(
                args.write_github_env,
                digest_date=digest_date.isoformat(),
                result=result,
            )

        print(
            json.dumps(
                {
                    "digest_date": digest_date.isoformat(),
                    **result.to_stats(),
                },
                ensure_ascii=False,
            )
        )

        if result.mode == "blocked":
            raise SystemExit(2)


def validate_items(
    items: list[dict[str, object]],
    *,
    min_candidates: int,
    min_translated_candidates: int,
    min_coverage: float,
    top_window: int,
    min_top_translated: int,
    mode_on_fail: str,
) -> ValidationResult:
    candidate_count = len(items)
    translated_count = sum(1 for item in items if item.get("translation_status") == "translated")
    coverage = translated_count / candidate_count if candidate_count else 0.0

    ranked = sorted(items, key=lambda row: int(row.get("_candidate_rank") or 10**9))
    top_items = ranked[:top_window] if top_window > 0 else []
    translated_top_count = sum(1 for item in top_items if item.get("translation_status") == "translated")

    checks = [
        (candidate_count >= min_candidates, f"candidate_count={candidate_count} < min_candidates={min_candidates}"),
        (
            translated_count >= min_translated_candidates,
            "translated_candidate_count="
            f"{translated_count} < min_translated_candidates={min_translated_candidates}",
        ),
        (
            coverage >= min_coverage,
            f"candidate_coverage={coverage:.2%} < min_coverage={min_coverage:.2%}",
        ),
        (
            translated_top_count >= min_top_translated,
            "translated_top_candidate_count="
            f"{translated_top_count} < min_top_translated={min_top_translated}",
        ),
    ]

    failed_reasons = [reason for ok, reason in checks if not ok]
    if not failed_reasons:
        return ValidationResult(
            mode="normal",
            reason="",
            candidate_count=candidate_count,
            translated_count=translated_count,
            translated_top_count=translated_top_count,
            coverage=coverage,
        )

    return ValidationResult(
        mode=mode_on_fail,
        reason="; ".join(failed_reasons),
        candidate_count=candidate_count,
        translated_count=translated_count,
        translated_top_count=translated_top_count,
        coverage=coverage,
    )


def write_github_env(path: str, *, digest_date: str, result: ValidationResult) -> None:
    # Keep the env file contract minimal and explicit for workflow steps.
    lines = [
        f"DIGEST_DATE={digest_date}",
        f"DIGEST_MODE={result.mode}",
        f"DIGEST_VALIDATION_REASON={result.reason}",
        f"DIGEST_CANDIDATE_COUNT={result.candidate_count}",
        f"DIGEST_TRANSLATED_CANDIDATE_COUNT={result.translated_count}",
        f"DIGEST_TRANSLATED_TOP_CANDIDATE_COUNT={result.translated_top_count}",
        f"DIGEST_CANDIDATE_COVERAGE={result.coverage}",
    ]
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
