"""The profile's «Статистика»: the user's own ranked All Pick history read the way a stats site does.

From the saved OpenDota history (me.py: every ranked All Pick match with hero, K/D/A, duration,
start time and party size) and two more OpenDota lists fetched with it — the players the user
played with (`peers`) and every hero's record with and against the user (`heroes`):
  - heroes: games, win rate, average K/D/A and KDA, the last game, the win rate of the last 30 days
    against the earlier one (trend);
  - when: win rate by hour of the day and by weekday (the computer's local time), by match length;
  - streaks and tilt: the win rate of the next game after 1, 2, 3+ losses (and wins) in a row, and by
    the game's number in a session (games less than SESSION_GAP apart);
  - party: solo against party games, and the players most often with the user;
  - matchups: the enemy heroes the user loses to most, the allied heroes the user wins with most;
  - records: the longest win and loss streaks, most kills, the longest game.
Small samples are kept out where a share would mean nothing (MIN_* below).
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict

SESSION_GAP = 90 * 60          # a pause longer than this starts a new session
MIN_HOUR_GAMES = 8
MIN_MATCHUP_GAMES = 8
TREND_DAYS = 30
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
HOUR_BLOCKS = [(0, 6, "ночь 0–6"), (6, 12, "утро 6–12"), (12, 18, "день 12–18"), (18, 24, "вечер 18–24")]
DURATION_BLOCKS = [(0, 25), (25, 35), (35, 45), (45, 999)]


def _won(m: dict) -> bool:
    return (m["player_slot"] < 128) == bool(m["radiant_win"])


def _wr(w: int, g: int) -> float | None:
    return round(w / g, 4) if g else None


def _row(games: int, wins: int, **extra) -> dict:
    return {"games": games, "wins": wins, "wr": _wr(wins, games), **extra}


def stats(data: dict, now: float | None = None) -> dict:
    now = now or time.time()
    matches = sorted((m for m in data.get("matches") or [] if m.get("hero_id") and m.get("start_time")),
                     key=lambda m: m["start_time"])
    if not matches:
        return {"games": 0}
    results = [_won(m) for m in matches]

    # ---- heroes ----
    per: dict[int, dict] = defaultdict(lambda: {"games": 0, "wins": 0, "k": 0, "d": 0, "a": 0, "last": 0,
                                                 "recent": [0, 0], "dur": 0})
    since = now - TREND_DAYS * 86400
    for m, won in zip(matches, results):
        h = per[m["hero_id"]]
        h["games"] += 1
        h["wins"] += won
        h["k"] += m.get("kills") or 0
        h["d"] += m.get("deaths") or 0
        h["a"] += m.get("assists") or 0
        h["dur"] += m.get("duration") or 0
        h["last"] = max(h["last"], m["start_time"])
        if m["start_time"] >= since:
            h["recent"][0] += 1
            h["recent"][1] += won
    heroes = []
    for hid, h in per.items():
        g = h["games"]
        rg, rw = h["recent"]
        older_g, older_w = g - rg, h["wins"] - rw
        trend = round(rw / rg - older_w / older_g, 4) if rg >= 5 and older_g >= 5 else None
        heroes.append({"hero": hid, **_row(g, h["wins"]), "k": round(h["k"] / g, 1), "d": round(h["d"] / g, 1),
                       "a": round(h["a"] / g, 1), "kda": round((h["k"] + h["a"]) / max(h["d"], 1), 2),
                       "last": h["last"], "recent_games": rg, "recent_wr": _wr(rw, rg), "trend": trend,
                       "minutes": round(h["dur"] / g / 60, 1)})
    heroes.sort(key=lambda r: -r["games"])

    # ---- when ----
    by_hour = [[0, 0] for _ in range(24)]
    by_day = [[0, 0] for _ in range(7)]
    by_len = [[0, 0] for _ in DURATION_BLOCKS]
    for m, won in zip(matches, results):
        t = time.localtime(m["start_time"])
        by_hour[t.tm_hour][0] += 1
        by_hour[t.tm_hour][1] += won
        by_day[t.tm_wday][0] += 1
        by_day[t.tm_wday][1] += won
        minutes = (m.get("duration") or 0) / 60
        b = next(i for i, (lo, hi) in enumerate(DURATION_BLOCKS) if lo <= minutes < hi)
        by_len[b][0] += 1
        by_len[b][1] += won
    hours = [_row(g, w, hour=i) for i, (g, w) in enumerate(by_hour)]
    blocks = []
    for lo, hi, label in HOUR_BLOCKS:
        g = sum(by_hour[i][0] for i in range(lo, hi))
        w = sum(by_hour[i][1] for i in range(lo, hi))
        blocks.append(_row(g, w, label=label))
    days = [_row(g, w, day=WEEKDAYS[i]) for i, (g, w) in enumerate(by_day)]
    lengths = [_row(g, w, label=(f"до {hi} мин" if lo == 0 else f"после {lo} мин" if hi == 999 else f"{lo}–{hi} мин"))
               for (lo, hi), (g, w) in zip(DURATION_BLOCKS, by_len)]

    # ---- streaks and tilt ----
    after_loss = defaultdict(lambda: [0, 0])     # n losses in a row before -> [games, wins]
    after_win = defaultdict(lambda: [0, 0])
    run_kind, run = None, 0
    best_win = best_loss = cur_win = cur_loss = 0
    in_session = defaultdict(lambda: [0, 0])
    session_no = 0
    prev_t = None
    for m, won in zip(matches, results):
        t = m["start_time"]
        if prev_t is None or t - prev_t > SESSION_GAP:
            session_no = 0
            run_kind, run = None, 0               # a streak doesn't carry over a break
        session_no += 1
        in_session[min(session_no, 4)][0] += 1
        in_session[min(session_no, 4)][1] += won
        if run_kind is False:
            after_loss[min(run, 3)][0] += 1
            after_loss[min(run, 3)][1] += won
        elif run_kind is True:
            after_win[min(run, 3)][0] += 1
            after_win[min(run, 3)][1] += won
        run = run + 1 if run_kind == won else 1
        run_kind = won
        cur_win = cur_win + 1 if won else 0
        cur_loss = 0 if won else cur_loss + 1
        best_win, best_loss = max(best_win, cur_win), max(best_loss, cur_loss)
        prev_t = t + (m.get("duration") or 0)
    overall = _wr(sum(results), len(results))
    tilt = {
        "after_loss": [_row(*after_loss[n], streak=n) for n in (1, 2, 3)],
        "after_win": [_row(*after_win[n], streak=n) for n in (1, 2, 3)],
        "session": [_row(*in_session[n], game=n) for n in (1, 2, 3, 4)],
    }
    advice = None
    l3 = tilt["after_loss"][2]
    if l3["games"] >= 10 and overall is not None and l3["wr"] is not None and l3["wr"] < overall - 0.04:
        advice = (f"После трёх поражений подряд ты выигрываешь {l3['wr'] * 100:.0f}% против обычных "
                  f"{overall * 100:.0f}%: после третьего поражения лучше сделать перерыв.")
    late = tilt["session"][3]
    if not advice and late["games"] >= 15 and late["wr"] is not None and overall is not None and late["wr"] < overall - 0.04:
        advice = (f"Четвёртая и дальше игра подряд — {late['wr'] * 100:.0f}% побед против обычных "
                  f"{overall * 100:.0f}%: длинные сессии тебе не идут.")
    tilt["advice"] = advice

    # ---- party ----
    solo = [w for m, w in zip(matches, results) if (m.get("party_size") or 1) <= 1]
    party = [w for m, w in zip(matches, results) if (m.get("party_size") or 1) > 1]
    peers = [{"account_id": p.get("account_id"), "name": p.get("personaname"),
              **_row(p.get("with_games") or 0, p.get("with_win") or 0),
              "against": _row(p.get("against_games") or 0, p.get("against_win") or 0), "last": p.get("last_played")}
             for p in data.get("peers") or [] if (p.get("with_games") or 0) >= 3]
    peers.sort(key=lambda p: -p["games"])

    # ---- matchups (OpenDota's per-hero list: with / against the user) ----
    against, allied = [], []
    for h in data.get("heroes_vs") or []:
        hid = int(h.get("hero_id") or 0)
        if not hid:
            continue
        if (h.get("against_games") or 0) >= MIN_MATCHUP_GAMES:
            against.append({"hero": hid, **_row(h["against_games"], h.get("against_win") or 0)})
        if (h.get("with_games") or 0) >= MIN_MATCHUP_GAMES:
            allied.append({"hero": hid, **_row(h["with_games"], h.get("with_win") or 0)})
    against.sort(key=lambda r: r["wr"])
    allied.sort(key=lambda r: -r["wr"])

    kills = max(matches, key=lambda m: m.get("kills") or 0)
    longest = max(matches, key=lambda m: m.get("duration") or 0)
    return {
        "games": len(matches), "wins": sum(results), "wr": overall,
        "first": matches[0]["start_time"], "last": matches[-1]["start_time"],
        "heroes": heroes,
        "when": {"hours": hours, "blocks": blocks, "days": days, "lengths": lengths,
                 "best_block": max((b for b in blocks if b["games"] >= MIN_HOUR_GAMES), key=lambda b: b["wr"], default=None),
                 "worst_block": min((b for b in blocks if b["games"] >= MIN_HOUR_GAMES), key=lambda b: b["wr"], default=None)},
        "tilt": tilt,
        "party": {"solo": _row(len(solo), sum(solo)), "party": _row(len(party), sum(party)), "peers": peers[:12]},
        "matchups": {"hard": against[:8], "easy": list(reversed(against[-5:])) if len(against) > 8 else [],
                     "with_best": allied[:6], "with_worst": list(reversed(allied[-5:])) if len(allied) > 6 else []},
        "records": {"win_streak": best_win, "loss_streak": best_loss,
                    "kills": {"value": kills.get("kills") or 0, "hero": kills["hero_id"], "match": kills["match_id"]},
                    "longest": {"minutes": round((longest.get("duration") or 0) / 60), "hero": longest["hero_id"],
                                "match": longest["match_id"], "win": _won(longest)},
                    "avg_minutes": round(statistics.mean((m.get("duration") or 0) for m in matches) / 60, 1)},
    }
