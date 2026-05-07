"""Apply SQLite migrations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collector.storage.migrations import migrate_database


DEFAULT_MESSAGES_DB = PROJECT_ROOT / "data/messages.sqlite3"
DEFAULT_SPOOL_DB = PROJECT_ROOT / "data/spool.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply SQLite migrations.")
    parser.add_argument("--messages-db", default=str(DEFAULT_MESSAGES_DB))
    parser.add_argument("--spool-db", default=str(DEFAULT_SPOOL_DB))
    parser.add_argument(
        "--target",
        choices=["all", "messages", "spool"],
        default="all",
    )
    args = parser.parse_args()

    if args.target in {"all", "messages"}:
        applied = migrate_database(
            args.messages_db,
            PROJECT_ROOT / "migrations/messages",
            require_fts5=True,
        )
        print(f"messages migrations applied: {', '.join(applied) or 'none'}")

    if args.target in {"all", "spool"}:
        applied = migrate_database(
            args.spool_db,
            PROJECT_ROOT / "migrations/spool",
        )
        print(f"spool migrations applied: {', '.join(applied) or 'none'}")


if __name__ == "__main__":
    main()

