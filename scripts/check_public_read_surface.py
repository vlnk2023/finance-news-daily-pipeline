"""Check anonymous read surface for views vs base tables."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpSessionLike(Protocol):
    def get(
        self,
        endpoint: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> "HttpResponseLike": ...


class HttpResponseLike(Protocol):
    status_code: int


@dataclass(frozen=True)
class UrlLibResponse:
    status_code: int


class UrlLibSession:
    def get(
        self,
        endpoint: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> UrlLibResponse:
        query = urlencode(params)
        url = f"{endpoint}?{query}"
        request = Request(url=url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                status_code = int(getattr(response, "status", 200))
        except HTTPError as exc:
            status_code = exc.code
        except URLError:
            status_code = 0
        return UrlLibResponse(status_code=status_code)


@dataclass(frozen=True)
class RelationCheck:
    relation: str
    status_code: int
    ok: bool
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Supabase public read surface.")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    parser.add_argument(
        "--publishable-key",
        default=os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
    )
    parser.add_argument(
        "--expect-base-table-open",
        action="store_true",
        help="Expect base tables to be publicly readable (pre-restriction mode).",
    )
    parser.add_argument(
        "--base-table-mode",
        choices=("restricted", "open", "dontcare"),
        default="restricted",
        help="Expected public access mode for base tables.",
    )
    parser.add_argument(
        "--skip-if-missing",
        action="store_true",
        help="Exit successfully when SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY is missing.",
    )
    parser.add_argument(
        "--allow-missing-public-views",
        action="store_true",
        help="Allow public_* views to be absent with 404 during fallback rollout.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()

    url = args.supabase_url.rstrip("/")
    key = args.publishable_key
    if not url or not key:
        if args.skip_if_missing:
            print("[SURFACE] SKIP missing SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY")
            return
        raise SystemExit("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY are required.")

    if args.expect_base_table_open:
        base_table_mode = "open"
    else:
        base_table_mode = args.base_table_mode

    headers = {
        "apikey": key,
        "authorization": f"Bearer {key}",
    }
    session = UrlLibSession()

    checks = [
        check_relation(
            session,
            url,
            headers,
            relation="public_daily_digests",
            select="digest_date",
            timeout_seconds=args.timeout_seconds,
            should_be_open=True,
            allow_missing=args.allow_missing_public_views,
        ),
        check_relation(
            session,
            url,
            headers,
            relation="public_pipeline_runs",
            select="job_type",
            timeout_seconds=args.timeout_seconds,
            should_be_open=True,
            allow_missing=args.allow_missing_public_views,
        ),
        check_relation(
            session,
            url,
            headers,
            relation="daily_digests",
            select="digest_date",
            timeout_seconds=args.timeout_seconds,
            should_be_open=base_table_mode == "open",
            skip_expectation=base_table_mode == "dontcare",
        ),
        check_relation(
            session,
            url,
            headers,
            relation="pipeline_runs",
            select="job_type",
            timeout_seconds=args.timeout_seconds,
            should_be_open=base_table_mode == "open",
            skip_expectation=base_table_mode == "dontcare",
        ),
    ]

    failed = [check for check in checks if not check.ok]
    for check in checks:
        marker = "OK" if check.ok else "FAIL"
        print(f"[SURFACE] {marker} relation={check.relation} status={check.status_code} detail={check.detail}")
    if failed:
        raise SystemExit(1)


def check_relation(
    session: HttpSessionLike,
    supabase_url: str,
    headers: dict[str, str],
    *,
    relation: str,
    select: str,
    timeout_seconds: float,
    should_be_open: bool,
    skip_expectation: bool = False,
    allow_missing: bool = False,
) -> RelationCheck:
    endpoint = f"{supabase_url}/rest/v1/{relation}"
    response = session.get(
        endpoint,
        params={"select": select, "limit": "1"},
        headers=headers,
        timeout=timeout_seconds,
    )
    is_open = response.status_code == 200
    if allow_missing and response.status_code == 404:
        return RelationCheck(
            relation=relation,
            status_code=response.status_code,
            ok=True,
            detail="missing-allowed",
        )
    if skip_expectation:
        return RelationCheck(
            relation=relation,
            status_code=response.status_code,
            ok=True,
            detail="dontcare",
        )
    if should_be_open:
        ok = is_open
        detail = "expected-open"
    else:
        ok = not is_open
        detail = "expected-restricted"
    return RelationCheck(
        relation=relation,
        status_code=response.status_code,
        ok=ok,
        detail=detail,
    )


if __name__ == "__main__":
    main()
