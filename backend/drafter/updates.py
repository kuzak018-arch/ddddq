"""Updates of the app: a newer installer from this project's GitHub releases, downloaded, checked
and handed to the shell to install.

The repository is public, so its releases can be read without a token: the newest vX.Y.Z release
with `Dota.Drafter_X.Y.Z_x64-setup.exe` and `….exe.sha256` (the release build attaches both). A
download is kept only when its SHA-256 matches that file. The shell (Rust, `install_update`) then
runs the installer over the old version in passive mode, which keeps the settings and data in
%LOCALAPPDATA%\\DotaDrafter. Another repository can be named in DRAFTER_RELEASES_REPO.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading

import httpx

from . import config

RELEASES_REPO = os.environ.get("DRAFTER_RELEASES_REPO", "kuzak018-arch/ddddq")
API = "https://api.github.com/repos/{repo}/releases?per_page=30"
DIR = config.DATA / "updates"
EXE = re.compile(r"^Dota[ .]Drafter_(\d+\.\d+\.\d+)_x64-setup\.exe$")
_lock = threading.Lock()


class UpdateError(RuntimeError):
    pass


def parse_version(v: str | None) -> tuple[int, int, int] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", (v or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _get(url: str, **kw) -> httpx.Response:
    headers = {"User-Agent": config.USER_AGENT, "Accept": "application/vnd.github+json"}
    return httpx.get(url, timeout=kw.pop("timeout", 20), follow_redirects=True, headers=headers, **kw)


def latest() -> dict:
    """The newest version release of RELEASES_REPO: version, notes and the installer with its checksum."""
    try:
        r = _get(API.format(repo=RELEASES_REPO))
    except httpx.HTTPError as e:
        raise UpdateError(f"нет связи с GitHub: {e}") from e
    if r.status_code == 404:
        raise UpdateError(f"в {RELEASES_REPO} ещё нет ни одного выпуска")
    if r.status_code == 403:
        raise UpdateError("GitHub временно ограничил запросы, попробуй через час")
    if r.status_code != 200:
        raise UpdateError(f"GitHub ответил {r.status_code}")
    releases = r.json()
    if not isinstance(releases, list):
        raise UpdateError("GitHub ответил в непонятном виде")
    best = None   # (version, release, installer, checksum): the highest vX.Y.Z that carries both files
    for rel in releases:
        version = parse_version(rel.get("tag_name"))
        if not version or rel.get("draft") or rel.get("prerelease"):
            continue   # «seed-data» and the like are not versions
        assets = {a.get("name"): a for a in rel.get("assets") or []}
        exe = next((a for n, a in assets.items() if n and EXE.match(n)), None)
        sha = assets.get(exe["name"] + ".sha256") if exe else None
        if exe and sha and (best is None or version > best[0]):
            best = (version, rel, exe, sha)
    if best is None:
        raise UpdateError(f"в {RELEASES_REPO} ещё нет выпуска с установщиком и контрольной суммой")
    version, rel, exe, sha = best
    return {
        "version": ".".join(map(str, version)),
        "notes": (rel.get("body") or "").strip(),
        "published": rel.get("published_at"),
        "page": rel.get("html_url"),
        "exe": {"name": exe["name"], "url": exe["browser_download_url"], "size": exe.get("size")},
        "sha_url": sha["browser_download_url"],
    }


def ready(version: str | None = None) -> dict | None:
    """The downloaded and checked installer (the newest one, or of `version`), if there is one."""
    best = None
    for f in DIR.glob("*-setup.exe") if DIR.exists() else []:
        m = EXE.match(f.name)
        if m and (version is None or m.group(1) == version):
            v = parse_version(m.group(1))
            if best is None or v > best[0]:
                best = (v, f)
    return {"version": ".".join(map(str, best[0])), "path": str(best[1])} if best else None


def check(current: str) -> dict:
    cur = parse_version(current)
    rel = latest()
    newer = cur is not None and parse_version(rel["version"]) > cur
    return {"current": current, "latest": rel["version"], "newer": newer, "notes": rel["notes"],
            "published": rel["published"], "page": rel["page"], "size": rel["exe"]["size"],
            "ready": ready(rel["version"]) if newer else None, "repo": RELEASES_REPO}


def _expected_sha(url: str | None) -> str:
    if not url:
        raise UpdateError("у установщика нет контрольной суммы — скачивать не буду")
    try:
        r = _get(url)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise UpdateError(f"не скачал контрольную сумму: {e}") from e
    m = re.search(r"\b[0-9a-fA-F]{64}\b", r.text)
    if not m:
        raise UpdateError("контрольная сумма в непонятном виде")
    return m.group(0).lower()


def download(log) -> dict:
    """Downloads the newest installer into data/updates (a job). Keeps it only when the SHA-256
    matches; older downloads are removed."""
    with _lock:
        rel = latest()
        if have := ready(rel["version"]):
            log(f"Версия {rel['version']} уже скачана")
            return have
        want = _expected_sha(rel["sha_url"])
        DIR.mkdir(parents=True, exist_ok=True)
        name = rel["exe"]["name"].replace(" ", ".")
        part = DIR / (name + ".part")
        h = hashlib.sha256()
        log(f"Скачиваю {rel['exe']['name']}")
        try:
            with httpx.stream("GET", rel["exe"]["url"], timeout=60, follow_redirects=True,
                              headers={"User-Agent": config.USER_AGENT}) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or rel["exe"]["size"] or 0)
                done, step = 0, 0
                with part.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 16):
                        f.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        if total and done * 10 // total > step:
                            step = done * 10 // total
                            log(f"{step * 10}%")
        except httpx.HTTPError as e:
            part.unlink(missing_ok=True)
            raise UpdateError(f"не скачал установщик: {e}") from e
        if h.hexdigest() != want:
            part.unlink(missing_ok=True)
            raise UpdateError("контрольная сумма не совпала — файл удалён")
        exe = DIR / name
        part.replace(exe)
        for f in DIR.iterdir():
            if f != exe:
                f.unlink(missing_ok=True)
        log(f"Готово: {rel['version']} скачана и проверена")
        return {"version": rel["version"], "path": str(exe)}
