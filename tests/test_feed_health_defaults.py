from scripts.apply_feed_health_defaults import apply_defaults


def test_apply_defaults_populates_missing_health_fields() -> None:
    feed = {
        "feed_id": "tg_example",
        "source_id": "tg_example",
        "source_name": "Example",
        "platform": "telegram",
        "url": "https://t.me/s/example",
        "collect": {"runs_per_day": 2},
    }

    changed = apply_defaults(feed)

    assert changed is True
    assert feed["health"]["cadence"] == "active_daily"
    assert feed["health"]["expected_update_interval_hours"] == 48
    assert feed["health"]["stale_after_hours"] == 96.0


def test_apply_defaults_keeps_existing_health_fields() -> None:
    feed = {
        "feed_id": "tg_example",
        "source_id": "tg_example",
        "source_name": "Example",
        "platform": "telegram",
        "url": "https://t.me/s/example",
        "collect": {"runs_per_day": 1},
        "health": {
            "cadence": "low_frequency",
            "expected_update_interval_hours": 888,
            "stale_after_hours": 999,
        },
    }

    changed = apply_defaults(feed)

    assert changed is False
    assert feed["health"]["cadence"] == "low_frequency"
    assert feed["health"]["expected_update_interval_hours"] == 888
    assert feed["health"]["stale_after_hours"] == 999
