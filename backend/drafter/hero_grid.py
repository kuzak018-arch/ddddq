"""The user's Dota hero grid file (hero_grid_config.json in the Steam userdata folder): reading,
the Valve JSON layout it is written in, backups and a merge that only ever touches our own grids.

Safety rules, all enforced here and not only in the UI:
  * nothing is written while dota2.exe runs: Dota reads the file at start and rewrites it on exit,
    so a write under a running game would be lost (or worse, mixed with the game's own write);
  * every write is preceded by a backup copy, and the file is read back and compared afterwards;
    if anything differs the backup is put back;
  * grids are told apart by a name prefix. Anything without it is the user's and is written back
    exactly as it was read (the writer reproduces Valve's formatting byte for byte);
  * a file that is not the version-3 layout we know is never touched.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, dota_paths

PREFIX = "Драфтер · "
VERSION = 3
KEEP_BACKUPS = 20
FILE_NAME = "hero_grid_config.json"
CATEGORY_KEYS = ("category_name", "x_position", "y_position", "width", "height", "hero_ids")


class GridError(Exception):
    """Something the user can act on; the message is shown as it is."""


class DotaRunning(GridError):
    pass


# ---------- Valve's JSON layout --------------------------------------------------------------

def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.6f}"
    if isinstance(v, int):
        return str(v)
    if v is None:
        return "null"
    return json.dumps(v, ensure_ascii=False)


def _val(v, depth: int) -> str:
    if isinstance(v, dict):
        return _container("{", "}", list(v.items()), depth)
    if isinstance(v, list):
        return _container("[", "]", [(None, x) for x in v], depth)
    return _scalar(v)


def _container(opening: str, closing: str, items: list, depth: int) -> str:
    inner = "\t" * (depth + 1)
    lines = [opening]
    for i, (key, x) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if key is None:
            lines.append(f"{inner}{_val(x, depth + 1)}{comma}")
        elif isinstance(x, (dict, list)):
            lines.append(f"{inner}{json.dumps(key, ensure_ascii=False)}:\n{inner}{_val(x, depth + 1)}{comma}")
        else:
            lines.append(f"{inner}{json.dumps(key, ensure_ascii=False)}: {_scalar(x)}{comma}")
    lines.append("\t" * depth + closing)
    return "\n".join(lines)


def dumps(data: dict) -> str:
    """Tabs, one value per line, brackets on their own line, floats with six decimals, no final
    newline: exactly how the game writes the file, so untouched grids come back byte-identical."""
    return _val(data, 0)


def loads(text: str) -> dict:
    return json.loads(text.removeprefix("﻿"))


def check_shape(data) -> None:
    """Refuse anything but the layout we know (version 3), so a newer format is never mangled."""
    if not isinstance(data, dict) or data.get("version") != VERSION or not isinstance(data.get("configs"), list):
        raise GridError(f"файл сеток в незнакомом формате (ждём version {VERSION}): ничего не меняю")
    for c in data["configs"]:
        if not isinstance(c, dict) or not isinstance(c.get("config_name"), str) or not isinstance(c.get("categories"), list):
            raise GridError("в файле сеток есть запись неизвестного вида: ничего не меняю")
        for cat in c["categories"]:
            if not isinstance(cat, dict) or any(k not in cat for k in CATEGORY_KEYS):
                raise GridError("в файле сеток есть категория неизвестного вида: ничего не меняю")


def is_ours(cfg: dict) -> bool:
    return str(cfg.get("config_name", "")).startswith(PREFIX)


def merge(existing: dict, ours: list[dict]) -> dict:
    """Existing grids stay as they are, in their order. Our grids replace our earlier ones in the
    same place; new ones go to the end. Nothing of the user's is copied or rebuilt."""
    mine = {c["config_name"]: c for c in ours}
    configs: list[dict] = []
    placed: set[str] = set()
    for c in existing["configs"]:
        if is_ours(c):
            if c["config_name"] in mine:
                configs.append(mine[c["config_name"]])
                placed.add(c["config_name"])
            # an old grid of ours that is no longer wanted is dropped
        else:
            configs.append(c)
    configs += [c for name, c in mine.items() if name not in placed]
    return {**existing, "configs": configs}


# ---------- where the file is, is the game running ---------------------------------------------

def grid_path(account_id: int | None) -> Path | None:
    """The file for this account (it may not exist yet); None if Steam or the folder is missing."""
    steam = dota_paths.steam_path()
    if steam is None or not account_id:
        return None
    cfg = steam / "userdata" / str(account_id) / "570" / "remote" / "cfg"
    return cfg / FILE_NAME if cfg.is_dir() else None


def dota_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq dota2.exe", "/NH", "/FO", "CSV"], capture_output=True,
                             text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        raise GridError("не удалось проверить, запущена ли Дота: ничего не записываю") from None
    return "dota2.exe" in out.lower()


# ---------- backups ----------------------------------------------------------------------------

def backup_dir() -> Path:
    return config.DATA / "backups" / "hero_grid"


def make_backup(path: Path, tag: str = "") -> Path:
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = d / f"hero_grid_config-{stamp}{'-' + tag if tag else ''}.json"
    n = 1
    while dest.exists():  # two copies in one second
        dest = d / f"hero_grid_config-{stamp}{'-' + tag if tag else ''}-{n}.json"
        n += 1
    shutil.copy2(path, dest)
    for old in sorted(d.glob("hero_grid_config-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP_BACKUPS:]:
        old.unlink(missing_ok=True)
    return dest


def list_backups() -> list[dict]:
    d = backup_dir()
    if not d.exists():
        return []
    rows = []
    for p in sorted(d.glob("hero_grid_config-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append({"name": p.name, "time": st.st_mtime, "size": st.st_size})
    return rows


# ---------- reading and writing ----------------------------------------------------------------

def _read(path: Path) -> dict:
    if not path.exists():
        return {"version": VERSION, "configs": []}
    try:
        data = loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        raise GridError("не получилось прочитать файл сеток (он повреждён?): ничего не меняю") from None
    check_shape(data)
    return data


def status(account_id: int | None) -> dict:
    path = grid_path(account_id)
    out = {"path": str(path) if path else None, "found": path is not None, "exists": bool(path and path.exists()),
           "ours": [], "others": 0, "backups": list_backups(), "backup_dir": str(backup_dir()), "error": None}
    if path and path.exists():
        try:
            data = _read(path)
            out["ours"] = [c["config_name"] for c in data["configs"] if is_ours(c)]
            out["others"] = sum(1 for c in data["configs"] if not is_ours(c))
        except GridError as e:
            out["error"] = str(e)
    return out


def _write_verified(path: Path, new: dict, before: dict, ours_names: set[str], backup: Path | None) -> None:
    """Atomic write, then read back: the user's grids must be unchanged and ours must be as built."""
    tmp = path.with_name(path.name + ".drafter-tmp")
    try:
        tmp.write_text(dumps(new), encoding="utf-8", newline="")
        os.replace(tmp, path)
        after = _read(path)
        keep_before = [c for c in before["configs"] if not is_ours(c)]
        keep_after = [c for c in after["configs"] if not is_ours(c)]
        got = {c["config_name"]: c for c in after["configs"] if is_ours(c)}
        want = {c["config_name"]: c for c in new["configs"] if is_ours(c)}
        if keep_before != keep_after or got != want or set(got) != ours_names:
            raise GridError("после записи файл не совпал с задуманным")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        if backup is not None:
            shutil.copy2(backup, path)
        elif path.exists():
            path.unlink()  # there was no file before
        raise GridError(f"запись отменена, файл возвращён как был ({e})") from e


def apply(account_id: int | None, ours: list[dict]) -> dict:
    """Write our grids into the file (replacing our earlier ones). Raises GridError / DotaRunning."""
    path = grid_path(account_id)
    if path is None:
        raise GridError("не нашёл папку сеток Доты в Steam (userdata → 570 → remote → cfg)")
    if dota_running():
        raise DotaRunning("Дота запущена: закрой её полностью, иначе она перезапишет файл при выходе")
    before = _read(path)
    for c in ours:
        if not is_ours(c):
            raise GridError(f"имя сетки должно начинаться с «{PREFIX}»")
    new = merge(before, copy.deepcopy(ours))
    backup = make_backup(path) if path.exists() else None
    _write_verified(path, new, before, {c["config_name"] for c in ours}, backup)
    return {"written": [c["config_name"] for c in ours], "backup": backup.name if backup else None,
            "others": sum(1 for c in new["configs"] if not is_ours(c))}


# ---------- grids from the editor ------------------------------------------------------------

MAX_CONFIGS = 100
MAX_CATEGORIES = 10_000
NUMBER_KEYS = ("x_position", "y_position", "width", "height")


def clean_configs(configs: list, prefix: bool = True) -> list[dict]:
    """The editor's grids in the file's exact shape: numbers as floats (written with six decimals
    like the game does), hero ids as ints, names without markup. With `prefix` every name gets
    PREFIX, so a write can only ever add or replace our own grids."""
    if not isinstance(configs, list) or not configs:
        raise GridError("нет сеток для записи")
    if len(configs) > MAX_CONFIGS:
        raise GridError(f"больше {MAX_CONFIGS} сеток в одном файле")
    out, names = [], set()
    for c in configs:
        if not isinstance(c, dict) or not isinstance(c.get("config_name"), str) or not isinstance(c.get("categories"), list):
            raise GridError("сетка в непонятном виде")
        name = _clean_text(c["config_name"]).strip() or "Сетка"
        if prefix and not name.startswith(PREFIX):
            name = PREFIX + name
        if name in names:
            raise GridError(f"две сетки с одним именем «{name}»: переименуй одну")
        names.add(name)
        if len(c["categories"]) > MAX_CATEGORIES:
            raise GridError(f"в сетке «{name}» больше {MAX_CATEGORIES} категорий")
        cats = []
        for cat in c["categories"]:
            if not isinstance(cat, dict) or any(k not in cat for k in CATEGORY_KEYS):
                raise GridError(f"категория в непонятном виде в сетке «{name}»")
            try:
                # six decimals, as written: the read-back check compares exactly
                nums = {k: round(float(cat[k]), 6) for k in NUMBER_KEYS}
                heroes = [int(h) for h in cat["hero_ids"]]
            except (TypeError, ValueError):
                raise GridError(f"неверные числа в категории сетки «{name}»") from None
            if any(n != n or abs(n) > 100_000 for n in nums.values()):
                raise GridError(f"неверные числа в категории сетки «{name}»")
            cats.append({**cat, "category_name": _clean_text(str(cat["category_name"])), **nums, "hero_ids": heroes})
        out.append({**{k: v for k, v in c.items() if k not in ("config_name", "categories")}, "config_name": name, "categories": cats})
    return out


def _clean_text(s: str) -> str:
    """No markup characters, no line breaks, no leading # (a localisation key in Dota)."""
    for ch in "<>&\r\n\t":
        s = s.replace(ch, "")
    return s.lstrip("#")


def read_configs(account_id: int | None) -> dict:
    """The file's grids as they are, for the editor's import. Read only."""
    path = grid_path(account_id)
    if path is None:
        raise GridError("не нашёл папку сеток Доты в Steam (userdata → 570 → remote → cfg)")
    data = _read(path)
    return {"path": str(path), "exists": path.exists(),
            "configs": [{**c, "ours": is_ours(c)} for c in data["configs"]]}


def export_text(configs: list[dict]) -> str:
    return dumps({"version": VERSION, "configs": configs})


def remove_ours(account_id: int | None) -> dict:
    """Take our grids out again; the user's stay."""
    path = grid_path(account_id)
    if path is None or not path.exists():
        raise GridError("файла сеток нет, нечего убирать")
    if dota_running():
        raise DotaRunning("Дота запущена: закрой её полностью, иначе она перезапишет файл при выходе")
    before = _read(path)
    removed = [c["config_name"] for c in before["configs"] if is_ours(c)]
    if not removed:
        return {"removed": [], "backup": None}
    new = merge(before, [])
    backup = make_backup(path)
    _write_verified(path, new, before, set(), backup)
    return {"removed": removed, "backup": backup.name}


def restore(account_id: int | None, name: str) -> dict:
    """Put a backup back as the file. The current file is copied first, so a restore can be undone."""
    path = grid_path(account_id)
    if path is None:
        raise GridError("не нашёл папку сеток Доты в Steam")
    src = backup_dir() / name
    if src.name != name or not name.startswith("hero_grid_config-") or not src.is_file():
        raise GridError("такой копии нет")
    if dota_running():
        raise DotaRunning("Дота запущена: закрой её полностью, иначе она перезапишет файл при выходе")
    check_shape(loads(src.read_text(encoding="utf-8")))  # never put back something we could not read
    before_copy = make_backup(path, "before-restore") if path.exists() else None
    shutil.copy2(src, path)
    return {"restored": name, "backup": before_copy.name if before_copy else None}
