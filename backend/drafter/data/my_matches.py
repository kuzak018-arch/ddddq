"""The user's recent ranked All Pick matches from Stratz, each with an estimate of how they played.

One request brings the last TAKE matches with the user's own numbers, the hero's averages at
every minute for that hero, position and bracket (Stratz's `heroAverage`: the norm), Stratz's
IMP (its estimate of a player's impact, 0 = an average game for that hero) and the lane outcomes.
In a player's match list Stratz returns only that player, so the rest of the team (networth, IMP)
comes from one request per parsed match; parsed matches never change, so that is cached for good.

The estimate (`assess`) starts from IMP, as Stratz has it for every parsed match:
  IMP >= GOOD -> played well, IMP <= -GOOD -> played badly, between -> about average;
together with the result this gives one of six labels. Blame and credit are relative to the
team: "I threw" needs the rest of the team to have played clearly better than me (by more than
TEAM_GAP IMP), otherwise it was a loss together; the same for carrying, being carried and losing
despite playing well. Without the team's numbers the label follows IMP alone. Two or three reasons with numbers come
from comparing the user's numbers with the norm: networth, experience, last hits at 10 minutes,
deaths, damage to heroes and buildings, the lane, networth place in the team. It is approximate:
statistics miss much of what a player does, supports most of all.
"""

from __future__ import annotations

import json
import threading
import time

from .. import config
from . import me, stratz
from . import stratz_matches as sm

CACHE = me.DIR / "stratz_matches.json"
TAKE = 30
REFRESH_S = 20 * 60
GOOD = 10                    # IMP at or above: played well; at or below -GOOD: played badly
TEAM_GAP = 10                # the rest of the team must differ from me by more than this to put it on one side
# how much a deviation from the norm counts when picking reasons (tower damage is the noisiest);
# each deviation is capped at +-100% first, so one wild number can't push the others out
WEIGHTS = {"nw": 1.0, "xp": 0.8, "cs10": 0.8, "hd": 0.8, "td": 0.5, "deaths": 0.8}
RANKED, ALL_PICK_RANKED = 7, 22

LABELS = {
    ("win", "good"): ("carried", "вытащил"),
    ("win", "mid"): ("won_together", "выиграли вместе"),
    ("win", "bad"): ("team_carried", "затащила команда"),
    ("loss", "good"): ("lost_played_well", "проиграл, хотя сыграл хорошо"),
    ("loss", "mid"): ("lost_together", "проиграли вместе"),
    ("loss", "bad"): ("threw", "слил игру я"),
}

_Q_LIST = """{ player(steamAccountId: %d) { matches(request: {take: %d, lobbyTypeIds: [%d], gameModeIds: [%d]}) {
  id didRadiantWin durationSeconds startDateTime parsedDateTime bracket topLaneOutcome midLaneOutcome bottomLaneOutcome
  players(steamAccountId: %d) { heroId isRadiant isVictory position lane kills deaths assists numLastHits numDenies
    goldPerMinute experiencePerMinute networth heroDamage towerDamage imp award
    stats { lastHitsPerMinute networthPerMinute }
    heroAverage { time kills deaths assists networth cs xp heroDamage towerDamage } } } } }"""
_Q_TEAM = "{ match(id: %d) { players { steamAccountId heroId isRadiant position networth imp } } }"

_lock = threading.Lock()
_job: dict = {"status": "idle"}


def load() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"fetched": 0, "matches": {}}
    except ValueError:
        return {"fetched": 0, "matches": {}}


def _save(data: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE)


def _pos(p: str | None) -> int | None:
    return int(p[-1]) if p and p.startswith("POSITION_") else None


def compact(m: dict) -> dict:
    """The parts of a Stratz match we keep: the user's numbers and the norm at the end and at 10:00."""
    p = (m.get("players") or [{}])[0]
    dur = m.get("durationSeconds") or 0
    stats = p.get("stats") or {}
    lh = stats.get("lastHitsPerMinute") or []
    nwm = stats.get("networthPerMinute") or []
    avg = {a["time"]: a for a in p.get("heroAverage") or []}
    t_end = min(dur // 60, max(avg)) if avg else None
    norm = None
    if t_end is not None:
        end, ten = avg.get(t_end, {}), avg.get(10, {})
        norm = {"t": t_end, "nw": end.get("networth"), "xp": end.get("xp"), "kills": end.get("kills"),
                "deaths": end.get("deaths"), "assists": end.get("assists"), "hd": end.get("heroDamage"),
                "td": end.get("towerDamage"), "cs10": ten.get("cs"), "nw10": ten.get("networth")}
    return {
        "id": m["id"], "start": m.get("startDateTime"), "duration": dur, "radiant_win": m.get("didRadiantWin"),
        "parsed": bool(m.get("parsedDateTime")), "bracket": m.get("bracket"),
        "lanes": {"top": m.get("topLaneOutcome"), "mid": m.get("midLaneOutcome"), "bot": m.get("bottomLaneOutcome")},
        "me": {"hero": p.get("heroId"), "radiant": p.get("isRadiant"), "win": p.get("isVictory"), "pos": _pos(p.get("position")),
               "lane": p.get("lane"), "k": p.get("kills"), "d": p.get("deaths"), "a": p.get("assists"),
               "lh": p.get("numLastHits"), "dn": p.get("numDenies"), "gpm": p.get("goldPerMinute"),
               "xpm": p.get("experiencePerMinute"), "nw": p.get("networth"), "hd": p.get("heroDamage"),
               "td": p.get("towerDamage"), "imp": p.get("imp"), "award": p.get("award"),
               "cs10": sum(lh[:10]) if len(lh) >= 10 else None, "nw10": nwm[10] if len(nwm) > 10 else None},
        "norm": norm,
    }


def _refresh(force: bool) -> None:
    acc = config.settings().account_id
    data = load()
    try:
        if not acc:
            raise RuntimeError("не указан аккаунт: укажи Steam ID в «Настройки → Аккаунт»")
        sz = stratz.Stratz()
        try:
            _job.update(status="loading", step="list")
            ms = sz.q(_Q_LIST % (acc, TAKE, RANKED, ALL_PICK_RANKED, acc))["player"]["matches"] or []
            old = data.get("matches", {})
            fresh = {}
            for m in ms:
                rec = compact(m)
                prev = old.get(str(rec["id"]))
                if prev and prev.get("team"):
                    rec["team"] = prev["team"]
                fresh[str(rec["id"])] = rec
            # keep older matches that fell out of the window (a longer history over time)
            data["matches"] = {**old, **fresh}
            data["fetched"] = time.time()
            _save(data)
            todo = [r for r in fresh.values() if r["parsed"] and not r.get("team")]
            _job.update(step="teams", teams_total=len(todo), teams_done=0)
            for r in todo:
                if not sm._budget_ok(sm.FOREGROUND_FLOOR):
                    break
                try:
                    players = (sz.q(_Q_TEAM % r["id"])["match"] or {}).get("players") or []
                except RuntimeError:
                    continue
                r["team"] = [{"acc": x.get("steamAccountId"), "hero": x.get("heroId"), "radiant": x.get("isRadiant"),
                              "pos": _pos(x.get("position")), "nw": x.get("networth"), "imp": x.get("imp")} for x in players]
                data["matches"][str(r["id"])] = r
                _job["teams_done"] += 1
                _save(data)
        finally:
            sz.close()
        _job.update(status="done", error=None, finished=time.time())
    except Exception as e:
        _job.update(status="failed", error=f"{type(e).__name__}: {e}", finished=time.time())


def ensure_fresh(force: bool = False) -> dict:
    """Start a background refresh when the cache is older than REFRESH_S (or when forced)."""
    if not config.settings().stratz_token:
        return {"status": "no_token"}
    with _lock:
        if _job.get("status") == "loading":
            return dict(_job)
        if not force and time.time() - load().get("fetched", 0) < REFRESH_S:
            return dict(_job)
        _job.clear()
        _job.update(status="loading", started=time.time())
        threading.Thread(target=_refresh, args=(force,), name="my-matches", daemon=True).start()
    return dict(_job)


def job() -> dict:
    return dict(_job)


# ---------- the estimate ----------------------------------------------------------------------

_PHYSICAL = {(True, "SAFE_LANE"): "bot", (True, "OFF_LANE"): "top", (False, "SAFE_LANE"): "top",
             (False, "OFF_LANE"): "bot", (True, "MID_LANE"): "mid", (False, "MID_LANE"): "mid"}


def lane_result(rec: dict) -> str | None:
    """won / stomped / tie / lost / was_stomped, from the user's side; None if unknown."""
    p = rec["me"]
    lane = _PHYSICAL.get((bool(p.get("radiant")), p.get("lane")))
    out = (rec.get("lanes") or {}).get(lane) if lane else None
    if not out:
        return None
    if out == "TIE":
        return "tie"
    mine = "RADIANT" if p.get("radiant") else "DIRE"
    stomp = out.endswith("STOMP")
    return ("stomped" if stomp else "won") if out.startswith(mine) else ("was_stomped" if stomp else "lost")


def _k(v: float) -> str:
    return f"{v / 1000:.1f}k".replace(".0k", "k") if abs(v) >= 1000 else f"{v:.0f}"


def _pct(r: float) -> str:
    return f"{r * 100:+.0f}%"


def assess(rec: dict) -> dict:
    """Label, reasons and the numbers behind them for one match."""
    p, n = rec["me"], rec.get("norm")
    win = bool(p.get("win"))
    out: dict = {"win": win}
    if not rec.get("parsed") or p.get("imp") is None or not n:
        out["pending"] = "Stratz ещё не разобрал этот матч: оценка появится позже."
        return out
    imp = p["imp"]
    level = "good" if imp >= GOOD else "bad" if imp <= -GOOD else "mid"
    out["imp"] = imp
    t = max(1, n["t"])
    items = []   # (goodness: positive = good for the user, text)

    def ratio(name, mine, norm, text, floor=1.0, invert=False):
        if mine is None or norm is None or norm < floor:
            return
        r = mine / norm - 1
        g = max(-1.0, min(1.0, -r if invert else r)) * WEIGHTS[name]
        items.append((g, name, text.format(mine=_k(mine), norm=_k(norm), pct=_pct(r))))

    ratio("nw", p.get("nw"), n.get("nw"), "нетворс {mine} при норме {norm} к " + f"{t}-й минуте" + " ({pct})", floor=500)
    if p.get("xpm") is not None and n.get("xp"):
        ratio("xp", p["xpm"] * rec["duration"] / 60, n["xp"], "опыт {mine} при норме {norm} ({pct})", floor=500)
    ratio("cs10", p.get("cs10"), n.get("cs10"), "ластхитов к 10-й минуте {mine} при норме {norm} ({pct})", floor=10)
    ratio("hd", p.get("hd"), n.get("hd"), "урон по героям {mine} при норме {norm} ({pct})", floor=1000)
    ratio("td", p.get("td"), n.get("td"), "урон по строениям {mine} при норме {norm} ({pct})", floor=300)
    if p.get("d") is not None and n.get("deaths") is not None:
        nd, md = n["deaths"], p["d"]
        g = max(-1.0, min(1.0, (nd - md) / max(nd, 2))) * WEIGHTS["deaths"]
        items.append((g, "deaths", f"смертей {md} при норме {nd:.1f}"))
    lr = lane_result(rec)
    if lr:
        text = {"stomped": "линия выиграна с разгромом", "won": "линия выиграна", "tie": "линия вничью",
                "lost": "линия проиграна", "was_stomped": "линия проиграна с разгромом"}[lr]
        g = {"stomped": 0.5, "won": 0.25, "tie": 0.0, "lost": -0.25, "was_stomped": -0.5}[lr]
        items.append((g, "lane", text))
    team = rec.get("team") or []
    mates = [x for x in team if x["radiant"] == p.get("radiant")]
    if len(mates) == 5 and all(x.get("nw") is not None for x in mates):
        place = 1 + sum(1 for x in mates if x["nw"] > (p.get("nw") or 0))
        out["nw_place"] = place
        pos = p.get("pos")
        # a core expects to be near the top, a support near the bottom
        expect = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}.get(pos or 3, 3)
        items.append(((expect - place) * 0.08, "nw_place", f"{place}-й по нетворсу в команде"))
    # me = my hero on my side (unique there), so this doesn't depend on which account is configured
    others = [x["imp"] for x in mates if x.get("imp") is not None and x.get("hero") != p.get("hero")]
    if others:
        out["team_imp"] = round(sum(others) / len(others))
        # credit or blame only when the rest of the team really played differently from me
        if level == "bad" and out["team_imp"] <= imp + TEAM_GAP:
            level = "mid"
        elif level == "good" and out["team_imp"] >= imp - TEAM_GAP:
            level = "mid"
    out["label_key"], out["label"] = LABELS[("win" if win else "loss", level)]
    out["metrics"] = {name: round(g, 3) for g, name, _ in items}

    good = sorted((x for x in items if x[0] > 0.05), key=lambda x: -x[0])
    bad = sorted((x for x in items if x[0] < -0.05), key=lambda x: x[0])
    if level == "good":
        picked = good[:2]
    elif level == "bad":
        picked = bad[:2]
    else:
        picked = good[:1] + bad[:1]
    reasons = [f"IMP {imp:+d} (оценка вклада от Stratz)"] + [text for _, _, text in picked]
    if "team_imp" in out and out["label_key"] in ("team_carried", "lost_played_well", "carried", "threw"):
        reasons.append(f"средний IMP остальных в команде {out['team_imp']:+d}")
    out["reasons"] = reasons[:4]
    return out


def history(limit: int = TAKE) -> dict:
    data = load()
    recs = sorted(data.get("matches", {}).values(), key=lambda r: -(r.get("start") or 0))[:limit]
    rows = []
    for r in recs:
        a = assess(r)
        p = r["me"]
        rows.append({"id": r["id"], "start": r.get("start"), "duration": r.get("duration"), "hero": p.get("hero"),
                     "pos": p.get("pos"), "win": bool(p.get("win")), "k": p.get("k"), "d": p.get("d"), "a": p.get("a"),
                     "award": p.get("award"), **{k: v for k, v in a.items() if k != "win"}})
    losses = [x for x in rows if not x["win"] and "label_key" in x]
    wins = [x for x in rows if x["win"] and "label_key" in x]
    count = lambda xs, key: sum(1 for x in xs if x["label_key"] == key)
    summary = {
        "matches": len(rows), "rated": len(losses) + len(wins), "pending": sum(1 for x in rows if "pending" in x),
        "losses": len(losses), "losses_me": count(losses, "threw"), "losses_team": count(losses, "lost_played_well"),
        "losses_together": count(losses, "lost_together"),
        "wins": len(wins), "wins_me": count(wins, "carried"), "wins_team": count(wins, "team_carried"),
        "wins_together": count(wins, "won_together"),
    }
    return {"fetched": data.get("fetched"), "matches": rows, "summary": summary, "job": job(), "good_imp": GOOD}
