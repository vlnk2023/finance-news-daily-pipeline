"""Fill missing feed.health defaults in the feed registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "src/config/feed-registry.json"
DEFAULT_EXPECTED_INTERVAL_BY_CADENCE = {
    "active_daily": 48,
    "active_weekly": 240,
    "low_frequency": 720,
    "dormant": 2160,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing feed.health defaults.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("feed registry must be a JSON list")

    changed = 0
    for feed in data:
        if not isinstance(feed, dict):
            continue
        if apply_defaults(feed):
            changed += 1

    if args.dry_run:
        print(f"[HEALTH-DEFAULTS] dry-run changed={changed}")
        return

    registry_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[HEALTH-DEFAULTS] wrote registry changed={changed}")


def apply_defaults(feed: dict) -> bool:
    health = feed.get("health")
    if health is None:
        health = {}
        feed["health"] = health
    if not isinstance(health, dict):
        return False

    changed = False
    cadence = str(health.get("cadence") or infer_cadence(feed))
    if "cadence" not in health:
        health["cadence"] = cadence
        changed = True

    expected = health.get("expected_update_interval_hours")
    if expected in (None, "", 0):
        expected = DEFAULT_EXPECTED_INTERVAL_BY_CADENCE.get(cadence, 720)
        health["expected_update_interval_hours"] = expected
        changed = True

    stale_after = health.get("stale_after_hours")
    if stale_after in (None, "", 0):
        health["stale_after_hours"] = float(expected) * 2.0
        changed = True

    return changed


def infer_cadence(feed: dict) -> str:
    collect = feed.get("collect") or {}
    runs_per_day = int(collect.get("runs_per_day") or 0)
    if runs_per_day >= 2:
        return "active_daily"
    if runs_per_day == 1:
        return "active_weekly"
    return "low_frequency"


if __name__ == "__main__":
    main()
