"""Paths and settings shared by every part of the backend.

Development: everything lives in the repository (data/, reports/, .env).
Installed app (PyInstaller bundle): read-only files (shared/, the seed data) come from the bundle,
everything the app writes goes to %LOCALAPPDATA%/DotaDrafter (Program Files is not writable).
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    BUNDLE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DotaDrafter"
    SHARED = BUNDLE / "shared"
    SEED = BUNDLE / "seed"
else:
    ROOT = Path(__file__).resolve().parents[2]
    SHARED = ROOT / "shared"
    SEED = None
BACKEND = ROOT / "backend"
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
ENV_FILE = ROOT / ".env"

load_dotenv(ENV_FILE)

OPENDOTA = "https://api.opendota.com/api"
STRATZ = "https://api.stratz.com/graphql"
VALVE_PATCHES = "https://www.dota2.com/datafeed/patchnoteslist?language=english"
USER_AGENT = "dota-drafter/0.1 (personal draft helper)"

SEED_DIRS = ("constants", "icons", "model", "stratz")


def ensure_seed() -> list[str]:
    """First start of an installed app: copy the bundled data (constants, icons, trained model,
    Stratz builds) into the user's data folder. Never overwrites what is already there."""
    if not SEED or not SEED.exists():
        return []
    copied = []
    for name in SEED_DIRS:
        src, dst = SEED / name, DATA / name
        if src.exists() and not dst.exists():
            shutil.copytree(src, dst)
            copied.append(name)
    return copied


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


def write_env(**values: str) -> None:
    """Set keys in .env (keeping other lines and comments) and in the running process."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    for key, value in values.items():
        row = f"{key}={value}"
        for i, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == key:
                lines[i] = row
                break
        else:
            lines.append(row)
        os.environ[key] = value
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
