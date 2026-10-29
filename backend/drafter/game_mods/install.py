"""Putting the menu background and the fonts into Dota, and taking them out again.

Safety, enforced here and not only in the UI:
  * nothing is written while dota2.exe runs (it holds its files and would show a broken menu);
  * the background is one VPK of ours in game/dota_<voice language>/ — Dota mounts that folder's
    pak*_dir.vpk over its own files — so no file of the game is changed; a file of someone else's at
    our name is moved to our backup folder first and put back on removal;
  * fonts can only replace Valve's files in game/dota/panorama/fonts (fontconfig reads loose files,
    not packs): each original is copied once to our backup folder before it is overwritten, and
    «Убрать всё» copies them back (Steam's «Проверить целостность» restores them as well);
  * the user's own VPK packs («Свои VPK») go the same way as the background: each into a free
    pakNN_dir.vpk of the voice language folder, never over an existing file; only packs whose data
    is inside the _dir file are taken (a multi-part pak01_000.vpk… pack would be missing its parts);
  * Dota's settings are never changed: the voice language is only read (boot.vcfg, launch options).
Everything we wrote is listed in data/game_mods/manifest.json with its SHA-256.
Installation steps follow GridStudio's tested installer (scripts/installer.mjs,
https://github.com/linsisss/dota2-grid-toolkit, GPL-3.0-only).
"""

from __future__ import annotations

import functools
import hashlib
import json
import mmap
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

from .. import config, dota_paths, hero_grid, kv

PAK_NAME = "pak02_dir.vpk"  # the number GridStudio tested; another one is taken if pak02 is someone else's
FONT_CACHE = "fontconfig"   # %TEMP%\fontconfig: fontconfig's cache, stale after a font change
DEFAULT_LANGUAGE = "english"


class ModError(Exception):
    """Something the user can act on; shown as it is."""


# one change at a time: every install/remove reads the manifest, writes files, saves the manifest —
# two at once (a big VPK still copying and «Убрать всё») would lose one's record, and its file
# would stay in Dota's folder unaccounted for
_lock = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        with _lock:
            return fn(*a, **kw)
    return wrapper


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
        return {"background": None, "fonts": {}, "packs": []}


def _save_manifest(m: dict) -> None:
    root().mkdir(parents=True, exist_ok=True)
    tmp = _manifest_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _manifest_path())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_sha_cache: dict[str, tuple[int, int, str]] = {}


def _file_sha(path: Path) -> str | None:
    """SHA-256 of a file, read in pieces and remembered by size and time (the status is asked for
    every few seconds and a pack can be a gigabyte)."""
    try:
        st = path.stat()
        hit = _sha_cache.get(str(path))
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        _sha_cache[str(path)] = (st.st_size, st.st_mtime_ns, h.hexdigest())
        return h.hexdigest()
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
    old = m.get("background") or {}
    ours = old.get("path")
    if ours and Path(ours).parent == folder and (not Path(ours).exists() or _file_sha(Path(ours)) == old.get("sha256")):
        taken = {p["path"] for p in m.get("packs", [])}
        if ours not in taken:
            return Path(ours)
    first = folder / PAK_NAME
    if not first.exists():
        return first
    return _free_pak(folder)


def _free_pak(folder: Path, start: int = 3) -> Path:
    for n in range(start, 100):
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
    ours = {(m.get("background") or {}).get("path")} | {p["path"] for p in m.get("packs", [])}
    if folder.is_dir():
        out["other_packs"] = sorted(p.name for p in folder.glob("pak*_dir.vpk") if str(p) not in ours and p.name != "pak01_dir.vpk")
    out["packs"] = [{**p, "intact": _file_sha(Path(p["path"])) == p["sha256"]} for p in m.get("packs", [])]
    if m.get("background"):
        out["background_intact"] = _file_sha(Path(m["background"]["path"])) == m["background"]["sha256"]
    if m.get("fonts"):
        fonts = _fonts_dir(dota)
        out["fonts_intact"] = all(_file_sha(fonts / name) == sha for name, sha in m["fonts"].items())
    return out


# ---------- background -------------------------------------------------------------------------

@_locked
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


@_locked
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


@_locked
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
        _save_manifest(m)  # each file as it lands: a failure half-way still leaves «Убрать всё» able to undo it
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
        # the copy goes once it is back: the next install copies Valve's file of that day
        # (a game update may have changed it), not an older one kept from before
        saved.unlink()
    elif target.exists() and _file_sha(target) == sha:
        target.unlink()  # there was no such file of Valve's


@_locked
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


# ---------- the user's own packs ---------------------------------------------------------------

PACK_MAX = 1_500_000_000


def check_pack(blob) -> dict:
    """What is in a pack of the user's; ModError when Dota could not use it as one file."""
    from .vpk import vpk_entries
    try:
        version, entries = vpk_entries(blob)
    except ValueError as e:
        raise ModError(str(e)) from e
    if not entries:
        raise ModError("в VPK нет ни одного файла")
    split = [p for p, archive, size in entries if archive != 0x7FFF and size]
    if split:
        raise ModError("это многотомный VPK (данные в файлах _000.vpk, _001.vpk…): нужен один файл _dir.vpk, "
                       "в котором лежат все данные")
    top = sorted({p.split("/", 1)[0] for p, _, _ in entries})
    return {"version": version, "files": len(entries), "top": top[:12], "paths": [p for p, _, _ in entries]}


def _pack_paths(path: Path) -> set[str]:
    """The files a pack in the folder changes (its directory only: the file is mapped, not read)."""
    from .vpk import vpk_entries
    try:
        with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            return {p for p, _, _ in vpk_entries(mm)[1]}
    except (OSError, ValueError):
        return set()


@_locked
def install_pack(account_id: int | None, data: bytes | Path, name: str) -> dict:
    """Puts a VPK of the user's (its bytes, or a file the upload was streamed to) into the voice
    language folder under a free pakNN_dir.vpk."""
    src = Path(data) if isinstance(data, (str, Path)) else None
    size = src.stat().st_size if src else len(data)
    if size > PACK_MAX:
        raise ModError("VPK больше 1,5 ГБ")
    if size < 12:
        raise ModError("файл слишком короткий для VPK")
    if src:
        with src.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            info = check_pack(mm)
        sha = _file_sha(src)
    else:
        info = check_pack(data)
        sha = sha256(data)
    dota = _dota()
    _closed()
    language, _ = voice_language(dota, account_id)
    if language == DEFAULT_LANGUAGE:
        raise ModError("язык озвучки — английский: Дота не читает папку dota_english. Поставь в Доте другой язык озвучки "
                       "(Настройки → Звук → Язык озвучки) и повтори")
    folder = _language_dir(dota, language)
    folder.mkdir(parents=True, exist_ok=True)
    m = manifest()
    if any(p["sha256"] == sha and Path(p["path"]).exists() for p in m.get("packs", [])):
        raise ModError("этот VPK уже установлен")
    # the background pack keeps pak02; the user's packs start after it
    target = _free_pak(folder, 3)
    # which files another pack in the folder also changes: Dota uses one of them, not both
    mine = set(info["paths"])
    overlaps = []
    for other in sorted(folder.glob("pak*_dir.vpk")):
        if other.name == "pak01_dir.vpk":
            continue  # Valve's own pack of the language (voices)
        common = mine & _pack_paths(other)
        if common:
            overlaps.append({"pack": other.name, "files": len(common), "example": sorted(common)[0]})
    tmp = target.with_name(target.name + ".drafter-tmp")
    if src:
        shutil.copyfile(src, tmp)
    else:
        tmp.write_bytes(data)
    os.replace(tmp, target)
    if _file_sha(target) != sha:
        target.unlink(missing_ok=True)
        raise ModError("VPK записался с ошибкой: убрал его, попробуй ещё раз")
    entry = {"id": sha[:12], "name": Path(name).name[:120] or target.name, "path": str(target), "sha256": sha,
             "bytes": size, "files": info["files"], "top": info["top"], "language": language, "time": time.time()}
    m.setdefault("packs", []).append(entry)
    _save_manifest(m)
    return {**entry, "overlaps": overlaps}


def incoming_dir() -> Path:
    """Where an upload is streamed before it is checked and copied into Dota's folder."""
    return root() / "incoming"


def _remove_pack_file(entry: dict) -> None:
    path = Path(entry["path"])
    if path.exists() and _file_sha(path) == entry["sha256"]:
        path.unlink()  # a file someone changed or replaced since is left alone


@_locked
def remove_pack(pack_id: str) -> bool:
    _closed()
    m = manifest()
    packs = m.get("packs", [])
    entry = next((p for p in packs if p["id"] == pack_id), None)
    if entry is None:
        return False
    _remove_pack_file(entry)
    m["packs"] = [p for p in packs if p is not entry]
    _save_manifest(m)
    return True


@_locked
def remove_packs() -> bool:
    _closed()
    m = manifest()
    if not m.get("packs"):
        return False
    for entry in m["packs"]:
        _remove_pack_file(entry)
    m["packs"] = []
    _save_manifest(m)
    return True


@_locked
def remove_all() -> dict:
    _closed()
    return {"background": remove_background(), "fonts": remove_fonts(), "packs": remove_packs()}
