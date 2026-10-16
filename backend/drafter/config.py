"""Paths and settings shared by every part of the backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SHARED = ROOT / "shared"
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

load_dotenv(ROOT / ".env")

OPENDOTA = "https://api.opendota.com/api"
STRATZ = "https://api.stratz.com/graphql"
VALVE_PATCHES = "https://www.dota2.com/datafeed/patchnoteslist?language=english"
USER_AGENT = "dota-drafter/0.1 (personal draft helper)"


@dataclass(frozen=True)
class Settings:
    account_id: int | None
    stratz_token: str | None
    opendota_key: str | None


def settings() -> Settings:
    acc = os.getenv("DOTA_ACCOUNT_ID", "").strip()
    return Settings(
        account_id=int(acc) if acc.isdigit() else None,
        stratz_token=os.getenv("STRATZ_TOKEN", "").strip() or None,
        opendota_key=os.getenv("OPENDOTA_API_KEY", "").strip() or None,
    )
