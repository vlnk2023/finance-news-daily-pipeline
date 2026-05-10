from datetime import datetime, timezone

from scripts.audit_source_health import (
    classify_source_health,
    infer_cadence,
    parse_content_range_count,
    parse_iso_datetime,
)


def test_parse_content_range_count_handles_missing_or_invalid_values() -> None:
    assert parse_content_range_count("") == 0
    assert parse_content_range_count("0-0/*") == 0
    assert parse_content_range_count("0-9/10") == 10
    assert parse_content_range_count("junk") == 0


def test_infer_cadence_uses_runs_per_day_signal() -> None:
    assert infer_cadence({"collect": {"runs_per_day": 2}}) == "active_daily"
    assert infer_cadence({"collect": {"runs_per_day": 1}}) == "active_weekly"
    assert infer_cadence({"collect": {"runs_per_day": 0}}) == "low_frequency"


def test_parse_iso_datetime_supports_z_and_offset() -> None:
    assert parse_iso_datetime("2026-05-08T00:00:00Z") is not None
    assert parse_iso_datetime("2026-05-08T08:00:00+08:00") is not None
    assert parse_iso_datetime("not-a-date") is None


def test_classify_source_health_by_age_windows() -> None:
    now_utc = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    status_active, age_active = classify_source_health(
        "2026-05-08T10:00:00+00:00",
        5,
        now_utc=now_utc,
        expected_update_interval_hours=24,
        stale_after_hours=72,
    )
    status_quiet, age_quiet = classify_source_health(
        "2026-05-06T12:00:00+00:00",
        5,
        now_utc=now_utc,
        expected_update_interval_hours=24,
        stale_after_hours=72,
    )
    status_stale, age_stale = classify_source_health(
        "2026-05-01T12:00:00+00:00",
        5,
        now_utc=now_utc,
        expected_update_interval_hours=24,
        stale_after_hours=72,
    )

    assert status_active == "healthy_active"
    assert age_active is not None
    assert status_quiet == "healthy_quiet"
    assert age_quiet is not None
    assert status_stale == "stale"
    assert age_stale is not None


def test_classify_source_health_handles_no_data() -> None:
    now_utc = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
    status, age_hours = classify_source_health(
        "",
        0,
        now_utc=now_utc,
        expected_update_interval_hours=24,
        stale_after_hours=72,
    )
    assert status == "no_data"
    assert age_hours is None
