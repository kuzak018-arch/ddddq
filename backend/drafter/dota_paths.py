"""Locate Steam, the Dota 2 install and the user's Dota config files (read-only)."""

from __future__ import annotations

import winreg
from dataclasses import dataclass
from pathlib import Path

from . import kv, settings

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


def is_dota_dir(p: Path) -> bool:
    return (p / "game" / "dota").is_dir()


def auto_dota_path() -> Path | None:
    """The Dota install found through Steam's library folders."""
    steam = steam_path()
    if steam is None:
        return None
    for lib in library_paths(steam):
        p = lib / "steamapps" / "common" / DOTA_DIR_NAME
        if is_dota_dir(p):
            return p
    return None


def dota_path() -> Path | None:
    """The folder the user picked in the setup (if it still is a Dota install), else the one Steam knows."""
    manual = settings.load().dota_dir
    if manual and is_dota_dir(Path(manual)):
        return Path(manual)
    return auto_dota_path()


def find_dota_root(picked: Path) -> Path | None:
    """The «dota 2 beta» folder from whatever the user picked inside it (game, game/dota,
    game/bin/win64, dota2.exe) or the folder itself."""
    for p in (picked, *picked.parents):
        if is_dota_dir(p):
            return p
    return None


STEAM64_BASE = 76561197960265728


def steam_accounts() -> list[dict]:
    """Steam accounts that signed in on this PC (Steam's loginusers.vdf, read only) and those with a
    Dota folder in userdata: Friend ID, name, whether it was the last one and whether it has Dota."""
    steam = steam_path()
    if steam is None:
        return []
    out: dict[int, dict] = {}
    vdf = steam / "config" / "loginusers.vdf"
    if vdf.exists():
        users = kv.loads(vdf.read_text(encoding="utf-8", errors="replace")).get("users", {})
        for sid, u in users.items():
            if not (isinstance(u, dict) and str(sid).isdigit()) or int(sid) <= STEAM64_BASE:
                continue
            acc = int(sid) - STEAM64_BASE
            out[acc] = {"account_id": acc, "name": u.get("PersonaName") or u.get("AccountName"),
                        "recent": u.get("MostRecent") == "1", "ts": int(u.get("Timestamp") or 0)}
    userdata = steam / "userdata"
    if userdata.is_dir():
        for d in userdata.iterdir():
            if d.name.isdigit() and int(d.name) > 0:
                out.setdefault(int(d.name), {"account_id": int(d.name), "name": None, "recent": False, "ts": 0})
    for acc, a in out.items():
        a["dota"] = (userdata / str(acc) / "570").is_dir()
    return sorted(out.values(), key=lambda a: (not a["recent"], not a["dota"], -a["ts"]))


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
