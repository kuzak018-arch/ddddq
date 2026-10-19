"""Putting the menu background and the fonts into Dota, and taking them out again.

Safety, enforced here and not only in the UI:
  * nothing is written while dota2.exe runs (it holds its files and would show a broken menu);
  * the background is one VPK of ours in game/dota_<voice language>/ — Dota mounts that folder's
    pak*_dir.vpk over its own files — so no file of the game is changed; a file of someone else's at
    our name is moved to our backup folder first and put back on removal;
  * fonts can only replace Valve's files in game/dota/panorama/fonts (fontconfig reads loose files,
    not packs): each original is copied once to our backup folder before it is overwritten, and
    «Убрать всё» copies them back (Steam's «Проверить целостность» restores them as well);
  * Dota's settings are never changed: the voice language is only read (boot.vcfg, launch options).
Everything we wrote is listed in data/game_mods/manifest.json with its SHA-256.
Installation steps follow GridStudio's tested installer (scripts/installer.mjs,
https://github.com/linsisss/dota2-grid-toolkit, GPL-3.0-only).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from .. import config, dota_paths, hero_grid, kv

PAK_NAME = "pak02_dir.vpk"  # the number GridStudio tested; another one is taken if pak02 is someone else's
FONT_CACHE = "fontconfig"   # %TEMP%\fontconfig: fontconfig's cache, stale after a font change
DEFAULT_LANGUAGE = "english"


class ModError(Exception):
    """Something the user can act on; shown as it is."""


def root() -> Path:
    return config.DATA / "game_mods"


def backup_dir() -> Path:
    return root() / "backup"


def _manifest_path() -> Path:
    return root() / "manifest.json"


def manifest() -> dict:
    try:
        return json.loads(_manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"background": None, "fonts": {}}


def _save_manifest(m: dict) -> None:
    root().mkdir(parents=True, exist_ok=True)
    tmp = _manifest_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _manifest_path())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes())
    except OSError:
        return None


# ---------- where things are -------------------------------------------------------------------

def voice_language(dota: Path, account_id: int | None) -> tuple[str, str]:
    """(language, where it was read). The launch option -language wins over boot.vcfg, as in Dota."""
    if account_id:
        steam = dota_paths.steam_path()
        cfg = steam / "userdata" / str(account_id) / "config" / "localconfig.vdf" if steam else None
        if cfg and cfg.exists():
            try:
                node = kv.loads(cfg.read_text(encoding="utf-8", errors="replace"))
                for key in ("userlocalconfigstore", "software", "valve", "steam", "apps", "570"):
                    node = _child(node, key)
                options = str(_child(node, "launchoptions") or "")
                m = re.search(r"-language\s+([A-Za-z_]+)", options)
                if m:
                    return m.group(1).lower(), "параметры запуска Steam (-language)"
            except Exception:  # a broken localconfig.vdf must not stop the rest
                pass
    boot = dota / "game" / "dota" / "cfg" / "boot.vcfg"
    try:
        m = re.search(r'"AudioLanguage"\s+"([^"]*)"', boot.read_text(encoding="utf-8", errors="replace"))
        if m and m.group(1).strip():
            return m.group(1).strip().lower(), "настройки Доты (boot.vcfg)"
    except OSError:
        pass
    return DEFAULT_LANGUAGE, "по умолчанию"


def _child(node, key: str):
    """A KeyValues child by name, any letter case (Steam writes both «apps» and «Apps»)."""
    if not isinstance(node, dict):
        return {}
    return next((v for k, v in node.items() if k.lower() == key), {})


def _dota() -> Path:
    dota = dota_paths.dota_path()
    if dota is None:
        raise ModError("не нашёл Dota 2 в библиотеках Steam")
    return dota


def _closed() -> None:
    if hero_grid.dota_running():
        raise ModError("Дота запущена: закрой её полностью (в том числе из трея Steam) и повтори")


def _language_dir(dota: Path, language: str) -> Path:
    return dota / "game" / f"dota_{language}"


def _fonts_dir(dota: Path) -> Path:
    return dota / "game" / "dota" / "panorama" / "fonts"


def _pick_pak(folder: Path, m: dict) -> Path:
    """Our earlier pack's name, else pak02 if free, else the first free number from 03."""
    ours = (m.get("background") or {}).get("path")
    if ours and Path(ours).parent == folder:
        return Path(ours)
    first = folder / PAK_NAME
    if not first.exists():
        return first
    for n in range(3, 100):
        p = folder / f"pak{n:02d}_dir.vpk"
        if not p.exists():
            return p
    raise ModError("в папке языка нет свободного номера pakNN_dir.vpk")


def status(account_id: int | None) -> dict:
    m = manifest()
    out: dict = {"dota": None, "running": None, "language": None, "language_source": None, "folder": None,
                 "usable": False, "other_packs": [], "background": m.get("background"), "fonts": sorted(m.get("fonts", {})),
                 "fonts_intact": None, "background_intact": None, "menu_client": None, "error": None}
    try:
        from .menu import valve_meta
        meta = valve_meta()
        out["menu_client"] = f"{meta.get('client')} от {meta.get('date')}"
    except (OSError, ValueError):
        pass
    dota = dota_paths.dota_path()
    if dota is None:
        out["error"] = "не нашёл Dota 2 в библиотеках Steam"
        return out
    out["dota"] = str(dota)
    try:
        out["running"] = hero_grid.dota_running()
    except hero_grid.GridError as e:
        out["error"] = str(e)
    language, source = voice_language(dota, account_id)
    folder = _language_dir(dota, language)
    out.update(language=language, language_source=source, folder=str(folder), usable=language != DEFAULT_LANGUAGE)
    ours = (m.get("background") or {}).get("path")
    if folder.is_dir():
        out["other_packs"] = sorted(p.name for p in folder.glob("pak*_dir.vpk") if str(p) != ours and p.name != "pak01_dir.vpk")
    if m.get("background"):
        out["background_intact"] = _file_sha(Path(m["background"]["path"])) == m["background"]["sha256"]
    if m.get("fonts"):
        fonts = _fonts_dir(dota)
        out["fonts_intact"] = all(_file_sha(fonts / name) == sha for name, sha in m["fonts"].items())
    return out


# ---------- background -------------------------------------------------------------------------

def install_background(account_id: int | None, pack: bytes, info: dict) -> dict:
    dota = _dota()
    _closed()
    language, _ = voice_language(dota, account_id)
    if language == DEFAULT_LANGUAGE:
        raise ModError("язык озвучки — английский: Дота не читает папку dota_english. Поставь в Доте другой язык озвучки "
                       "(Настройки → Звук → Язык озвучки) и повтори")
    folder = _language_dir(dota, language)
    folder.mkdir(parents=True, exist_ok=True)
    m = manifest()
    old = m.get("background")
    target = _pick_pak(folder, m)
    # a file at our name that is not ours goes to our backup first
    if target.exists() and not (old and str(target) == old["path"]):
        backup_dir().mkdir(parents=True, exist_ok=True)
        saved = backup_dir() / f"{target.parent.name}__{target.name}"
        if not saved.exists():
            shutil.copy2(target, saved)
    # our earlier pack in another language folder goes away
    if old and Path(old["path"]) != target:
        _remove_background_file(old)
    tmp = target.with_name(target.name + ".drafter-tmp")
    tmp.write_bytes(pack)
    os.replace(tmp, target)
    if _file_sha(target) != sha256(pack):
        target.unlink(missing_ok=True)
        raise ModError("файл фона записался с ошибкой: убрал его, попробуй ещё раз")
    m["background"] = {"path": str(target), "sha256": sha256(pack), "bytes": len(pack), "language": language,
                       "time": time.time(), **info}
    _save_manifest(m)
    return {"path": str(target), "language": language, "bytes": len(pack)}


def _remove_background_file(entry: dict) -> None:
    path = Path(entry["path"])
    if path.exists() and _file_sha(path) == entry["sha256"]:
        path.unlink()
    saved = backup_dir() / f"{path.parent.name}__{path.name}"
    if saved.exists() and not path.exists():
        shutil.move(str(saved), path)


def remove_background() -> bool:
    _closed()
    m = manifest()
    if not m.get("background"):
        return False
    _remove_background_file(m["background"])
    m["background"] = None
    _save_manifest(m)
    return True


# ---------- fonts ------------------------------------------------------------------------------

def _clear_font_cache() -> None:
    cache = Path(os.environ.get("TEMP") or tempfile.gettempdir()) / FONT_CACHE
    shutil.rmtree(cache, ignore_errors=True)


def install_fonts(files: dict[str, bytes], info: dict) -> dict:
    """files: {Valve's file name (radiance-regular.otf …): data}."""
    from .fonts import DOTA_FONT_FILES
    if not files or any(name not in DOTA_FONT_FILES for name in files):
        raise ModError("неверный набор файлов шрифта")
    dota = _dota()
    _closed()
    fonts = _fonts_dir(dota)
    if not fonts.is_dir():
        raise ModError("не нашёл папку шрифтов Доты (game/dota/panorama/fonts)")
    m = manifest()
    ours: dict[str, str] = m.get("fonts", {})
    saved_dir = backup_dir() / "fonts"
    saved_dir.mkdir(parents=True, exist_ok=True)
    # Valve's originals once, before anything of ours is written over them
    for name in files:
        target, saved = fonts / name, saved_dir / name
        if target.exists() and not saved.exists() and _file_sha(target) != ours.get(name):
            shutil.copy2(target, saved)
    # files of ours that are not in the new set get Valve's back
    for name in [n for n in ours if n not in files]:
        _restore_font(fonts, name, ours[name])
        ours.pop(name)
    for name, data in files.items():
        tmp = fonts / (name + ".drafter-tmp")
        tmp.write_bytes(data)
        os.replace(tmp, fonts / name)
        ours[name] = sha256(data)
    m["fonts"] = ours
    m["font_info"] = {**info, "time": time.time()}
    _save_manifest(m)
    _clear_font_cache()
    return {"files": len(files), "folder": str(fonts)}


def _restore_font(fonts: Path, name: str, sha: str) -> None:
    saved = backup_dir() / "fonts" / name
    target = fonts / name
    if saved.exists():
        shutil.copy2(saved, target)
    elif target.exists() and _file_sha(target) == sha:
        target.unlink()  # there was no such file of Valve's


def remove_fonts() -> bool:
    _closed()
    m = manifest()
    if not m.get("fonts"):
        return False
    fonts = _fonts_dir(_dota())
    for name, sha in m["fonts"].items():
        _restore_font(fonts, name, sha)
    m["fonts"] = {}
    m.pop("font_info", None)
    _save_manifest(m)
    _clear_font_cache()
    return True


def remove_all() -> dict:
    _closed()
    return {"background": remove_background(), "fonts": remove_fonts()}
