"""«Кто заруинил»: a breakdown of one match, every one of the ten players rated and the one who lost
the game for their team named.

Data: OpenDota's match (free, no token; once the replay is parsed it has, per player, percentiles
against everyone's games on that hero — `benchmarks` — plus lane efficiency, wards, teamfights and
the kill log) and, with a Stratz token, Stratz's match (positions 1-5, IMP — its own estimate of a
player's impact —, lane outcomes, death times). Either alone is enough; both together are best. A
match OpenDota hasn't parsed is sent for parsing and the breakdown refines itself when it is.

The rating (0-100, 50 = an ordinary game on that hero) is a weighted mean of components, each
0..1 with 0.5 the norm:
  farm (GPM and last hits against the hero's games), experience, fights (hero damage, kill
  participation), survival (deaths and time dead per 10 minutes against what is usual for the
  role), objectives (tower damage), support (wards per minute, healing), the lane, and IMP.
Weights depend on the role: a support is not judged by farm, a core is not judged by wards.
Components without data drop out and the rest are renormalised.

The ruiner is the lowest rating of the losing team, named only when they are clearly below the
rest (RUIN_GAP); otherwise the loss was shared and the weakest is only shown. The winning team's
best is the MVP. Reasons are the player's weakest (or strongest) components, with their numbers.
Statistics miss much of a game — vision, positioning, saves — supports most of all: it is an
estimate, and the page says so.
"""

from __future__ import annotations

import json
import statistics
import time

from . import config
from .data import constants, stratz
from .data.http import OpenDota, RateLimited

DIR = config.DATA / "ruin"
RUIN_GAP = 6            # rating points the ruiner must be below the next one of the team
SURE_BELOW = 40         # ...and at most this, for a confident verdict
PARSE_RECHECK_S = 60    # a match sent for parsing is asked for again at most this often

ROLE_WEIGHTS = {
    "core": {"farm": 0.25, "xp": 0.10, "fight": 0.25, "survival": 0.20, "objectives": 0.10, "lane": 0.10},
    "support": {"farm": 0.05, "xp": 0.10, "fight": 0.25, "survival": 0.20, "support": 0.30, "lane": 0.10},
}
DEATHS_PER_10 = {"core": 1.5, "support": 2.0}       # usual deaths per 10 minutes
WARDS_PER_MIN = {4: 0.25, 5: 0.35}                   # usual wards (obs + sen) per minute
LANE_SCORE = {"stomped": 0.9, "won": 0.7, "tie": 0.5, "lost": 0.3, "was_stomped": 0.1}
LANE_TEXT = {"stomped": "линию разнёс", "won": "линию выиграл", "tie": "линия вничью",
             "lost": "линию проиграл", "was_stomped": "линию проиграл всухую"}
_PHYSICAL = {(True, "SAFE_LANE"): "bot", (True, "OFF_LANE"): "top", (False, "SAFE_LANE"): "top",
             (False, "OFF_LANE"): "bot", (True, "MID_LANE"): "mid", (False, "MID_LANE"): "mid"}
_OD_LANE = {1: "bot", 2: "mid", 3: "top"}            # OpenDota `lane`: 1 bottom, 2 middle, 3 top

_Q_FULL = """{ match(id: %d) { id didRadiantWin durationSeconds startDateTime parsedDateTime
  topLaneOutcome midLaneOutcome bottomLaneOutcome radiantNetworthLeads
  players { steamAccountId heroId isRadiant isVictory position lane kills deaths assists numLastHits numDenies
    goldPerMinute experiencePerMinute networth heroDamage towerDamage heroHealing imp award
    steamAccount { name } stats { deathEvents { time } } } } }"""
# the same with only the fields every other query here already uses: if Stratz renames one of the
# extra ones, the breakdown still gets positions, IMP and lanes
_Q_BASIC = """{ match(id: %d) { id didRadiantWin durationSeconds startDateTime parsedDateTime
  topLaneOutcome midLaneOutcome bottomLaneOutcome
  players { steamAccountId heroId isRadiant isVictory position lane kills deaths assists numLastHits numDenies
    goldPerMinute experiencePerMinute networth heroDamage towerDamage imp award } } }"""


class RuinError(RuntimeError):
    pass


# ---------- fetching ------------------------------------------------------------------------------

def _path(match_id: int):
    return DIR / f"{match_id}.json"


def _load(match_id: int) -> dict | None:
    try:
        return json.loads(_path(match_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(match_id: int, raw: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(match_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_path(match_id))


def _complete(raw: dict) -> bool:
    """Nothing more will come: OpenDota parsed it (or can't), and Stratz has it if there is a token."""
    od = raw.get("opendota")
    od_done = bool(od and od.get("version")) or raw.get("parse", {}).get("state") == "unavailable"
    sz_done = raw.get("stratz") is not None or not config.settings().stratz_token
    return od_done and sz_done


def _fetch_stratz(match_id: int) -> tuple[dict | None, str | None]:
    if not config.settings().stratz_token:
        return None, None
    try:
        sz = stratz.Stratz()
    except RuntimeError as e:
        return None, str(e)
    try:
        for q in (_Q_FULL, _Q_BASIC):
            try:
                m = sz.q(q % match_id).get("match")
            except RuntimeError as e:
                err = str(e)
                continue
            if m and m.get("players"):
                return m, None
            return None, "Stratz не знает этот матч"
        return None, err
    finally:
        sz.close()


def _fetch_opendota(match_id: int, raw: dict) -> tuple[dict | None, str | None]:
    od = OpenDota(timeout=30)
    try:
        try:
            m = od.get(f"/matches/{match_id}", retries=2)
        except RateLimited as e:
            return None, str(e)
        except Exception as e:     # 404 and the like
            return None, f"OpenDota: {str(e)[:160]}"
        if m and not m.get("version"):
            # not parsed yet: ask for the parse once, then check now and then
            st = raw.get("parse") or {}
            now = time.time()
            try:
                if not st.get("requested"):
                    res = od.post(f"/request/{match_id}") or {}
                    st = {"requested": now, "state": "queued", "job": (res.get("job") or {}).get("jobId")}
                elif now - st.get("requested", now) > 6 * 3600:
                    st["state"] = "unavailable"   # the replay has expired or is blocked
            except Exception as e:
                st = {"requested": now, "state": "unavailable", "error": str(e)[:160]}
            raw["parse"] = st
        return m or None, None
    finally:
        od.close()


def fetch(match_id: int, refresh: bool = False) -> dict:
    """The raw data of the match (cached for good once complete)."""
    raw = _load(match_id) or {"id": match_id}
    if not refresh and _complete(raw):
        return raw
    if not refresh and time.time() - raw.get("fetched", 0) < PARSE_RECHECK_S and (raw.get("opendota") or raw.get("stratz")):
        return raw
    od, od_err = _fetch_opendota(match_id, raw)
    sz, sz_err = _fetch_stratz(match_id)
    if od:
        raw["opendota"] = od
    if sz:
        raw["stratz"] = sz
    if not raw.get("opendota") and not raw.get("stratz"):
        raise RuinError(od_err or sz_err or "матч не найден")
    raw["errors"] = [e for e in (od_err, sz_err) if e]
    raw["fetched"] = time.time()
    _save(match_id, raw)
    return raw


# ---------- one table of players from either source -------------------------------------------------

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _npc(hero_id: int) -> str:
    h = constants.hero_by_id().get(hero_id)
    return f"npc_dota_hero_{h['key']}" if h else ""


def _lane_result(radiant: bool, lane: str | None, outcomes: dict) -> str | None:
    out = outcomes.get(lane) if lane else None
    if not out:
        return None
    if out == "TIE":
        return "tie"
    stomp = out.endswith("STOMP")
    return ("stomped" if stomp else "won") if out.startswith("RADIANT" if radiant else "DIRE") else ("was_stomped" if stomp else "lost")


def _infer_positions(players: list[dict]) -> None:
    """OpenDota has no positions: mid is the mid laner; of the others, the two richest are pos 1
    (safe lane) and 3 (off lane), the two poorest pos 5 (safe lane) and 4 (off lane)."""
    for radiant in (True, False):
        team = [p for p in players if p["radiant"] == radiant and not p.get("pos")]
        if not team:
            continue
        safe, off = ("bot", "top") if radiant else ("top", "bot")
        mid = [p for p in team if p.get("lane") == "mid"]
        if mid:
            max(mid, key=lambda p: p["nw"])["pos"] = 2
        rest = sorted((p for p in team if not p.get("pos")), key=lambda p: -p["nw"])
        cores, sups = rest[:2], rest[2:]
        if len(rest) == 4 and not mid:
            cores, sups = rest[:3], rest[3:]
        free_core = [1, 3] if mid else [1, 2, 3]
        for p in sorted(cores, key=lambda p: (p.get("lane") != safe, -p["nw"])):
            p["pos"] = free_core.pop(0) if free_core else 3
        for p in sorted(sups, key=lambda p: (p.get("lane") != off, p["nw"])):
            p["pos"] = 4 if not any(q.get("pos") == 4 for q in team) else 5


def table(raw: dict) -> dict:
    """The match as one structure, whichever sources there are."""
    od = raw.get("opendota") or {}
    sz = raw.get("stratz") or {}
    od_players = {p.get("hero_id"): p for p in od.get("players") or []}
    sz_players = {p.get("heroId"): p for p in sz.get("players") or []}
    heroes = list(dict.fromkeys([*od_players, *sz_players]))
    duration = od.get("duration") or sz.get("durationSeconds") or 0
    minutes = max(1.0, duration / 60)
    radiant_win = od["radiant_win"] if "radiant_win" in od else sz.get("didRadiantWin")
    outcomes = {"top": sz.get("topLaneOutcome"), "mid": sz.get("midLaneOutcome"), "bot": sz.get("bottomLaneOutcome")}
    deaths_by: dict[str, list[int]] = {}
    for p in od.get("players") or []:
        for k in p.get("kills_log") or []:
            deaths_by.setdefault(k.get("key"), []).append(int(k.get("time") or 0))
    players = []
    for hero in heroes:
        o, s = od_players.get(hero) or {}, sz_players.get(hero) or {}
        radiant = o["isRadiant"] if "isRadiant" in o else (o["player_slot"] < 128 if "player_slot" in o else bool(s.get("isRadiant")))
        lane = _PHYSICAL.get((radiant, s.get("lane"))) or _OD_LANE.get(o.get("lane"))
        pos = s.get("position")
        bench = {k: (v or {}).get("pct") for k, v in (o.get("benchmarks") or {}).items()}
        deaths_t = [e.get("time") for e in ((s.get("stats") or {}).get("deathEvents") or []) if e.get("time") is not None]
        if not deaths_t and o.get("kills_log") is not None:
            deaths_t = sorted(deaths_by.get(_npc(hero), []))
        p = {
            "hero": hero, "radiant": radiant,
            "win": bool(radiant_win) == radiant if radiant_win is not None else None,
            "name": o.get("personaname") or (s.get("steamAccount") or {}).get("name"),
            "acc": o.get("account_id") or s.get("steamAccountId"),
            "pos": int(pos[-1]) if isinstance(pos, str) and pos.startswith("POSITION_") else None,
            "lane": lane,
            "k": o.get("kills", s.get("kills")) or 0, "d": o.get("deaths", s.get("deaths")) or 0,
            "a": o.get("assists", s.get("assists")) or 0,
            "lh": o.get("last_hits", s.get("numLastHits")) or 0, "dn": o.get("denies", s.get("numDenies")) or 0,
            "gpm": o.get("gold_per_min", s.get("goldPerMinute")) or 0, "xpm": o.get("xp_per_min", s.get("experiencePerMinute")) or 0,
            "nw": o.get("net_worth", s.get("networth")) or 0,
            "hd": o.get("hero_damage", s.get("heroDamage")) or 0, "td": o.get("tower_damage", s.get("towerDamage")) or 0,
            "heal": o.get("hero_healing", s.get("heroHealing")) or 0,
            "wards": (o.get("obs_placed") or 0) + (o.get("sen_placed") or 0) if "obs_placed" in o else None,
            "dead_s": o.get("life_state_dead"),
            "lane_eff": o.get("lane_efficiency_pct"),
            "lane_result": _lane_result(radiant, lane, outcomes),
            "imp": s.get("imp"), "award": s.get("award") if s.get("award") not in (None, "NONE") else None,
            "bench": bench, "deaths_t": deaths_t,
            "items": [o.get(f"item_{i}") for i in range(6) if o.get(f"item_{i}")],
        }
        players.append(p)
    _infer_positions(players)
    for radiant in (True, False):
        team = [p for p in players if p["radiant"] == radiant]
        kills = sum(p["k"] for p in team) or 1
        for p in team:
            p["kp"] = (p["k"] + p["a"]) / kills
    adv = od.get("radiant_gold_adv") or sz.get("radiantNetworthLeads") or []
    return {"id": raw["id"], "duration": duration, "minutes": minutes, "radiant_win": radiant_win,
            "start": od.get("start_time") or sz.get("startDateTime"), "players": players, "gold_adv": list(adv),
            "parsed": bool(od.get("version")) or bool(sz.get("parsedDateTime")),
            "sources": [n for n, v in (("OpenDota", od), ("Stratz", sz)) if v]}


# ---------- rating -------------------------------------------------------------------------------

def _k(v: float) -> str:
    return f"{v / 1000:.1f}k".replace(".0k", "k") if abs(v) >= 1000 else f"{v:.0f}"


def _than(pct: float) -> str:
    return f"лучше {pct * 100:.0f}% игр на герое" if pct >= 0.5 else f"хуже {(1 - pct) * 100:.0f}% игр на герое"


def components(p: dict, m: dict, match_players: list[dict]) -> dict[str, tuple[float, str]]:
    """Each component as (score 0..1, the text with its number)."""
    role = "core" if (p.get("pos") or 1) <= 3 else "support"
    b = p["bench"]
    mins = m["minutes"]
    out: dict[str, tuple[float, str]] = {}
    if b.get("gold_per_min") is not None:
        farm = statistics.mean(x for x in (b.get("gold_per_min"), b.get("last_hits_per_min")) if x is not None)
        out["farm"] = (farm, f"GPM {p['gpm']} — {_than(b['gold_per_min'])}")
    else:   # no benchmarks: against the same role in this match
        same = [q["gpm"] for q in match_players if ((q.get("pos") or 1) <= 3) == (role == "core")]
        med = statistics.median(same) if same else p["gpm"]
        out["farm"] = (_clamp(0.5 + (p["gpm"] - med) / (2 * max(med, 1))), f"GPM {p['gpm']} при {med:.0f} у этих ролей в матче")
    if b.get("xp_per_min") is not None:
        out["xp"] = (b["xp_per_min"], f"XPM {p['xpm']} — {_than(b['xp_per_min'])}")
    kp = _clamp((p["kp"] - 0.25) / 0.5)
    hd = b.get("hero_damage_per_min")
    fight = statistics.mean([kp] + ([hd] if hd is not None else []))
    out["fight"] = (fight, f"участие в убийствах {p['kp'] * 100:.0f}%, урон по героям {_k(p['hd'])}")
    per10 = p["d"] / mins * 10
    norm = DEATHS_PER_10[role]
    surv = _clamp(1 - per10 / (2 * norm))
    text = f"{p['d']} {_deaths(p['d'])}"
    if p.get("dead_s"):
        text += f", {p['dead_s'] / 60:.0f} мин мёртвым"
        surv = _clamp(surv - max(0.0, p["dead_s"] / max(m["duration"], 1) - 0.12))
    out["survival"] = (surv, text)
    if role == "core":
        if b.get("tower_damage") is not None:
            out["objectives"] = (b["tower_damage"], f"урон по строениям {_k(p['td'])} — {_than(b['tower_damage'])}")
    else:
        parts = []
        if p.get("wards") is not None:
            usual = WARDS_PER_MIN.get(p.get("pos") or 5, 0.3) * mins
            parts.append((_clamp(0.5 * p["wards"] / max(usual, 1)), f"вардов {p['wards']}"))
        if b.get("hero_healing_per_min") is not None and p["heal"]:
            parts.append((b["hero_healing_per_min"], f"лечения {_k(p['heal'])}"))
        if parts:
            out["support"] = (statistics.mean(s for s, _ in parts), ", ".join(t for _, t in parts))
    if p.get("lane_result"):
        out["lane"] = (LANE_SCORE[p["lane_result"]], LANE_TEXT[p["lane_result"]])
    elif p.get("lane_eff") is not None:
        out["lane"] = (_clamp(p["lane_eff"] / 100), f"эффективность на линии {p['lane_eff']:.0f}%")
    return out


def _deaths(n: int) -> str:
    return "смерть" if n % 10 == 1 and n % 100 != 11 else "смерти" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "смертей"


def rate(p: dict, m: dict) -> dict:
    comps = components(p, m, m["players"])
    role = "core" if (p.get("pos") or 1) <= 3 else "support"
    w = ROLE_WEIGHTS[role]
    have = {k: v for k, v in comps.items() if k in w}
    total_w = sum(w[k] for k in have) or 1
    composite = sum(w[k] * have[k][0] for k in have) / total_w
    score = composite
    if p.get("imp") is not None:
        score = 0.5 * composite + 0.5 * _clamp(0.5 + p["imp"] / 50)
    ranked = sorted(have.items(), key=lambda kv: kv[1][0])
    return {"rating": round(score * 100), "parts": {k: round(v[0] * 100) for k, v in have.items()},
            "worst": [t for k, (s, t) in ranked if s < 0.45][:3],
            "best": [t for k, (s, t) in reversed(ranked) if s > 0.55][:3]}


def _turn(m: dict, losers_radiant: bool) -> dict | None:
    """The losing team's biggest lead: the game they had and gave away."""
    adv = m["gold_adv"]
    if not adv:
        return None
    sign = 1 if losers_radiant else -1
    lead, minute = max(((sign * v, i) for i, v in enumerate(adv)), default=(0, 0))
    return {"lead": round(lead), "minute": minute} if lead >= 3000 else None


def analyze(raw: dict) -> dict:
    m = table(raw)
    for p in m["players"]:
        p.update(rate(p, m))
    out = {k: m[k] for k in ("id", "duration", "radiant_win", "start", "gold_adv", "parsed", "sources")}
    out["players"] = sorted(m["players"], key=lambda p: (not p["radiant"], p.get("pos") or 9))
    out["parse"] = raw.get("parse")
    out["errors"] = raw.get("errors") or []
    if m["radiant_win"] is None or len(m["players"]) < 10:
        out["verdict"] = None
        return out
    losers = sorted((p for p in m["players"] if not p["win"]), key=lambda p: p["rating"])
    winners = sorted((p for p in m["players"] if p["win"]), key=lambda p: -p["rating"])
    low, nxt = losers[0], losers[1]
    gap = nxt["rating"] - low["rating"]
    if gap >= RUIN_GAP:
        kind = "sure" if low["rating"] <= SURE_BELOW else "likely"
    else:
        kind = "together"
    low["tag"] = "ruiner" if kind != "together" else "weakest"
    winners[0]["tag"] = "mvp"
    if losers[-1]["rating"] >= 60 and losers[-1] is not low:
        losers[-1]["tag"] = "unlucky"       # played well and still lost
    if winners[-1]["rating"] <= 40 and winners[-1] is not winners[0]:
        winners[-1]["tag"] = "carried"      # won without doing much
    out["verdict"] = {"kind": kind, "ruiner": low["hero"], "gap": gap, "mvp": winners[0]["hero"],
                      "turn": _turn(m, not m["radiant_win"])}
    return out


def breakdown(match_id: int, refresh: bool = False) -> dict:
    return analyze(fetch(match_id, refresh))
