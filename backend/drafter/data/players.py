"""Any player by Friend ID or a profile link, searched by hand ("Профиль → Найти игрока").

Only what the user typed is looked up: players of the current match are never pulled in by
themselves. The data are what the open sites publish:
  - OpenDota: the profile (name, avatar, the rank medal from the in-game profile card, which it
    has even for closed profiles), wins and losses, heroes, recent matches;
  - Stratz (with the user's token): the name, matches with positions, its win and match counts.
Dotabuff has no API and blocks programs, so it is only a link. A player who has not switched on
"Expose Public Match Data" is anonymous in every match: no site has their matches, and the
answer says so instead of showing zeros.
"""

from __future__ import annotations

import re
import threading
import time

import httpx

from .. import config
from . import stratz
from .http import OpenDota

STEAM64_BASE = 76561197960265728
CACHE_S = 10 * 60
HEROES_TOP = 12
RECENT = 20
_cache: dict[int, tuple[float, dict]] = {}
_lock = threading.Lock()


class PlayerError(ValueError):
    pass


_SITE_ID = re.compile(r"(?:dotabuff\.com|stratz\.com|opendota\.com)/(?:[a-z]{2}/)?players/(\d+)", re.I)
_PROFILES = re.compile(r"steamcommunity\.com/profiles/(\d{17})", re.I)
_VANITY = re.compile(r"steamcommunity\.com/id/([A-Za-z0-9_-]{2,64})", re.I)
_STEAM3 = re.compile(r"\[U:1:(\d+)\]")


def account_from_number(n: int) -> int:
    """A Friend ID (32-bit account id) or a 64-bit Steam ID, as the account id."""
    if STEAM64_BASE < n < STEAM64_BASE + 2 ** 32:
        return n - STEAM64_BASE
    if 0 < n < 2 ** 32:
        return n
    raise PlayerError("это не Steam ID: Friend ID — число до 10 цифр, Steam ID64 — 17 цифр с 7656119…")


def resolve_vanity(name: str) -> int:
    """steamcommunity.com/id/<name>: Steam's own XML page of the profile holds its Steam ID64
    (no API key needed)."""
    try:
        r = httpx.get(f"https://steamcommunity.com/id/{name}/?xml=1", timeout=15, follow_redirects=True,
                      headers={"User-Agent": config.USER_AGENT})
    except httpx.HTTPError as e:
        raise PlayerError(f"Steam не ответил: {e}") from e
    m = re.search(r"<steamID64>(\d{17})</steamID64>", r.text)
    if not m:
        raise PlayerError(f"в Steam нет профиля с адресом «{name}»")
    return account_from_number(int(m.group(1)))


def parse_target(text: str, resolve=resolve_vanity) -> int:
    """Friend ID, Steam ID64, [U:1:…], or a link to Steam, Dotabuff, Stratz or OpenDota."""
    t = (text or "").strip()
    if not t:
        raise PlayerError("введи Friend ID или ссылку на профиль")
    for rx in (_SITE_ID, _STEAM3):
        if m := rx.search(t):
            return account_from_number(int(m.group(1)))
    if m := _PROFILES.search(t):
        return account_from_number(int(m.group(1)))
    if m := _VANITY.search(t):
        return resolve(m.group(1))
    digits = re.sub(r"[\s-]", "", t)
    if digits.isdigit():
        return account_from_number(int(digits))
    raise PlayerError("не понял: нужен Friend ID (из профиля в Доте), Steam ID64 или ссылка на профиль Steam, "
                       "Dotabuff, Stratz или OpenDota")


# ---------- the sites -------------------------------------------------------------------------

def _opendota(acc: int) -> dict:
    od = OpenDota(min_interval=1.05)
    try:
        prof = od.get(f"/players/{acc}") or {}
        if not (prof.get("profile") or {}).get("account_id"):
            return {"found": False, "rank_tier": prof.get("rank_tier"), "leaderboard": prof.get("leaderboard_rank")}
        wl = od.get(f"/players/{acc}/wl") or {}
        recent = od.get(f"/players/{acc}/recentMatches") or []
        heroes = od.get(f"/players/{acc}/heroes") or []
    finally:
        od.close()
    p = prof["profile"]
    heroes = sorted((h for h in heroes if h.get("games")), key=lambda h: -h["games"])[:HEROES_TOP]
    return {
        "found": True, "name": p.get("personaname"), "avatar": p.get("avatarfull"), "plus": bool(p.get("plus")),
        "country": p.get("loccountrycode"), "last_login": p.get("last_login"),
        "rank_tier": prof.get("rank_tier"), "leaderboard": prof.get("leaderboard_rank"),
        "wins": wl.get("win"), "losses": wl.get("lose"),
        "heroes": [{"hero": int(h["hero_id"]), "games": h["games"], "wins": h.get("win", 0), "last": h.get("last_played")}
                   for h in heroes],
        "matches": [{"id": m["match_id"], "hero": m.get("hero_id"), "win": bool(m.get("radiant_win")) == (m.get("player_slot", 0) < 128),
                     "k": m.get("kills"), "d": m.get("deaths"), "a": m.get("assists"), "duration": m.get("duration"),
                     "start": m.get("start_time"), "gpm": m.get("gold_per_min"), "xpm": m.get("xp_per_min"),
                     "lh": m.get("last_hits"), "pos": None, "ranked": m.get("lobby_type") == 7}
                    for m in recent[:RECENT]],
    }


_Q_STRATZ = """{ player(steamAccountId: %d) { winCount matchCount firstMatchDate lastMatchDate
  steamAccount { name avatar isAnonymous seasonRank smurfFlag }
  matches(request: {take: %d}) { id didRadiantWin durationSeconds startDateTime lobbyType
    players(steamAccountId: %d) { heroId isVictory kills deaths assists position goldPerMinute experiencePerMinute numLastHits } } } }"""


_UNKNOWN = re.compile(r'Cannot query field \\?"(\w+)\\?"')


def query_dropping_unknown(sz, query: str, tries: int = 6) -> dict:
    """The query, minus any plain field Stratz says it does not have (its schema changes, and
    only part of these fields could be checked against it): the rest still comes back."""
    for _ in range(tries):
        try:
            return sz.q(query)
        except RuntimeError as e:
            m = _UNKNOWN.search(str(e))
            if not m or not re.search(rf"\b{m.group(1)}\b(?!\s*[({{])", query):
                raise
            query = re.sub(rf"\s\b{m.group(1)}\b(?!\s*[({{])", "", query, count=1)
    return sz.q(query)


def _stratz(acc: int) -> dict | None:
    if not config.settings().stratz_token:
        return None
    sz = stratz.Stratz()
    try:
        p = (query_dropping_unknown(sz, _Q_STRATZ % (acc, RECENT, acc)) or {}).get("player") or {}
    finally:
        sz.close()
    sa = p.get("steamAccount") or {}
    out = {"name": sa.get("name"), "anonymous": bool(sa.get("isAnonymous")), "rank_tier": sa.get("seasonRank"),
           "smurf": sa.get("smurfFlag"), "wins": p.get("winCount"), "games": p.get("matchCount"),
           "first": p.get("firstMatchDate"), "last": p.get("lastMatchDate"), "matches": []}
    for m in p.get("matches") or []:
        me = (m.get("players") or [{}])[0]
        pos = me.get("position") or ""
        out["matches"].append({"id": m["id"], "hero": me.get("heroId"), "win": bool(me.get("isVictory")),
                               "k": me.get("kills"), "d": me.get("deaths"), "a": me.get("assists"),
                               "duration": m.get("durationSeconds"), "start": m.get("startDateTime"),
                               "gpm": me.get("goldPerMinute"), "xpm": me.get("experiencePerMinute"), "lh": me.get("numLastHits"),
                               "pos": int(pos[-1]) if pos.startswith("POSITION_") else None,
                               "ranked": m.get("lobbyType") in ("RANKED", 7)})
    return out


def _site_error(e: Exception, site: str) -> str:
    text = str(e)
    if "429" in text or "limit" in text.lower():
        return f"{site}: лимит запросов, попробуй через минуту"
    if "401" in text or "403" in text:
        return f"{site}: токен не принят — проверь его в «Настройки → Аккаунт»" if site == "Stratz" else f"{site}: доступ закрыт"
    return f"{site}: не ответил ({text[:120]})"


def lookup(text: str, refresh: bool = False) -> dict:
    acc = parse_target(text)
    with _lock:
        hit = _cache.get(acc)
    if hit and not refresh and time.time() - hit[0] < CACHE_S:
        return hit[1]
    results: dict = {}

    def run(name, fn):
        try:
            results[name] = fn(acc)
        except Exception as e:     # one site down must not hide the other
            results[name + "_error"] = _site_error(e, "OpenDota" if name == "od" else "Stratz")

    threads = [threading.Thread(target=run, args=a) for a in (("od", _opendota), ("sz", _stratz))]
    for t in threads:
        t.start()
    deadline = time.time() + 60
    for t in threads:
        t.join(max(0.0, deadline - time.time()))
    late = False
    for (name, site), t in zip((("od", "OpenDota"), ("sz", "Stratz")), threads):
        if t.is_alive() and name not in results and name + "_error" not in results:
            results[name + "_error"] = f"{site}: не ответил за минуту"
            late = True
    out = merge(acc, results.get("od"), results.get("sz"))
    out["errors"] = [results[k] for k in ("od_error", "sz_error") if k in results]
    out["fetched"] = time.time()
    if not late:   # a site that did not answer in time is asked again next search, not cached as «nothing»
        with _lock:
            _cache[acc] = (time.time(), out)
    return out


def merge(acc: int, od: dict | None, sz: dict | None) -> dict:
    """One picture from both sites. Matches: Stratz's when it has them (they carry positions),
    else OpenDota's. Wins and losses: OpenDota's all-time record, else Stratz's counts."""
    od = od or {}
    sz = sz or {}
    wins, losses = od.get("wins"), od.get("losses")
    if not (wins or losses) and sz.get("games"):
        wins, losses = sz.get("wins") or 0, (sz["games"] - (sz.get("wins") or 0))
    games = (wins or 0) + (losses or 0)
    matches = sz.get("matches") or od.get("matches") or []
    closed = not games and not matches
    out = {
        "account_id": acc, "steam64": acc + STEAM64_BASE,
        "name": od.get("name") or sz.get("name"), "avatar": od.get("avatar"),
        "rank_tier": od.get("rank_tier") or sz.get("rank_tier"), "leaderboard": od.get("leaderboard"),
        "plus": od.get("plus", False), "country": od.get("country"), "smurf": sz.get("smurf"),
        "wins": wins, "losses": losses, "games": games, "winrate": (wins / games) if games else None,
        "heroes": od.get("heroes") or [], "matches": matches,
        "sources": {"opendota": bool(od.get("found")), "stratz": bool(sz)},
        "closed": closed, "found": bool(od.get("found") or sz.get("name") or od.get("rank_tier")),
        "links": {"dotabuff": f"https://www.dotabuff.com/players/{acc}", "stratz": f"https://stratz.com/players/{acc}",
                  "opendota": f"https://www.opendota.com/players/{acc}",
                  "steam": f"https://steamcommunity.com/profiles/{acc + STEAM64_BASE}"},
    }
    if closed:
        out["closed_note"] = ("Данных матчей на Stratz, OpenDota и Dotabuff нет: игрок не открыл «Общедоступные данные матчей» "
                              "в настройках Доты (или ещё не играл). Его матчи у всех сайтов записаны как «Аноним».")
    return out
