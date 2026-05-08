"""Finance News Daily collector package."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


# Load project-level .env for local development without overriding real env vars.
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)
