from types import SimpleNamespace

import pytest

from scripts import check_public_read_surface
from scripts.check_public_read_surface import check_relation


class FakeSession:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

    def get(self, *_args, **_kwargs):
        return SimpleNamespace(status_code=self._status_code)


def test_check_relation_open_expected_open() -> None:
    result = check_relation(
        FakeSession(200),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="public_daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=True,
    )
    assert result.ok is True


def test_check_relation_open_expected_restricted() -> None:
    result = check_relation(
        FakeSession(200),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=False,
    )
    assert result.ok is False


def test_check_relation_restricted_expected_restricted() -> None:
    result = check_relation(
        FakeSession(401),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=False,
    )
    assert result.ok is True


def test_check_relation_dontcare_mode() -> None:
    result = check_relation(
        FakeSession(401),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=True,
        skip_expectation=True,
    )
    assert result.ok is True
    assert result.detail == "dontcare"


def test_check_relation_allows_missing_public_view() -> None:
    result = check_relation(
        FakeSession(404),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="public_daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=True,
        allow_missing=True,
    )
    assert result.ok is True
    assert result.detail == "missing-allowed"


def test_check_relation_does_not_allow_restricted_public_view() -> None:
    result = check_relation(
        FakeSession(401),
        "https://example.supabase.co",
        {"apikey": "k", "authorization": "Bearer k"},
        relation="public_daily_digests",
        select="digest_date",
        timeout_seconds=1,
        should_be_open=True,
        allow_missing=True,
    )
    assert result.ok is False


def test_main_skip_if_missing(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(
        check_public_read_surface.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(
            supabase_url="",
            publishable_key="",
            expect_base_table_open=False,
            base_table_mode="restricted",
            skip_if_missing=True,
            allow_missing_public_views=False,
            timeout_seconds=1.0,
        ),
    )
    check_public_read_surface.main()
    out = capsys.readouterr().out
    assert "SKIP missing" in out


def test_main_fail_if_missing_without_skip(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(
        check_public_read_surface.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(
            supabase_url="",
            publishable_key="",
            expect_base_table_open=False,
            base_table_mode="restricted",
            skip_if_missing=False,
            allow_missing_public_views=False,
            timeout_seconds=1.0,
        ),
    )
    with pytest.raises(SystemExit):
        check_public_read_surface.main()
