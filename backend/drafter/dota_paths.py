"""Locate Steam, the Dota 2 install and the user's Dota config files (read-only)."""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from pathlib import Path

from . import kv

DOTA_DIR_NAME = "dota 2 beta"


def steam_path() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return None


def library_paths(steam: Path) -> list[Path]:
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return [steam]
    libs = kv.loads(vdf.read_text(encoding="utf-8", errors="replace")).get("libraryfolders", {})
    return [Path(v["path"]) for v in libs.values() if isinstance(v, dict) and "path" in v]


def dota_path() -> Path | None:
    steam = steam_path()
    if steam is None:
        return None
    for lib in library_paths(steam):
        p = lib / "steamapps" / "common" / DOTA_DIR_NAME
        if (p / "game" / "dota").is_dir():
            return p
    return None


def gsi_dir(dota: Path) -> Path:
    return dota / "game" / "dota" / "cfg" / "gamestate_integration"


def user_cfg_dir(account_id: int) -> Path | None:
    steam = steam_path()
    if steam is None:
        return None
    p = steam / "userdata" / str(account_id) / "570" / "local" / "cfg"
    return p if p.is_dir() else None


@dataclass(frozen=True)
class VideoMode:
    width: int
    height: int
    fullscreen: bool  # exclusive fullscreen: overlay and window capture won't work
    borderless: bool

    @property
    def label(self) -> str:
        if self.fullscreen:
            return "полноэкранный (эксклюзивный)"
        return "окно без рамки" if self.borderless else "оконный"


def video_mode(account_id: int) -> VideoMode | None:
    cfg = user_cfg_dir(account_id)
    if cfg is None or not (cfg / "video.txt").exists():
        return None
    v = kv.loads((cfg / "video.txt").read_text(encoding="utf-8", errors="replace")).get("video.cfg", {})
    return VideoMode(
        width=int(v.get("setting.defaultres", 0)),
        height=int(v.get("setting.defaultresheight", 0)),
        fullscreen=v.get("setting.fullscreen") == "1",
        borderless=v.get("setting.nowindowborder") == "1",
    )
