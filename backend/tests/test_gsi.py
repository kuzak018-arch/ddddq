import json
import urllib.error
import urllib.request

import pytest

from drafter import gsi, kv
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "hero_index.json").exists(), reason="нужны константы")

AM, AXE, PUDGE, LION = 1, 2, 14, 26
EMPTY = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": None, "my_hero": None, "phase": "idle"}


def payload(state, team="radiant", hero=None, match="777", draft=None):
    p = {"provider": {"name": "Dota 2", "appid": 570},
         "map": {"matchid": match, "game_state": state},
         "player": {"team_name": team, "activity": "playing"},
         "hero": {"id": hero or 0, "name": f"npc_dota_hero_{hero}" if False else ""}}
    if draft:
        p["draft"] = draft
    return p


class Session:
    """Minimal stand-in for api.session: applies changes like session.patch."""

    def __init__(self):
        self.s = dict(EMPTY)

    def apply(self, **changes):
        self.s = {**self.s, **changes}


def test_phases_side_and_my_hero():
    sess = Session()
    t = gsi.Tracker(sess.apply)
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", "dire"), sess.s)
    assert sess.s["phase"] == "draft" and sess.s["side"] == "dire"
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", "dire", hero=PUDGE), sess.s)
    assert sess.s["my_hero"] == PUDGE and sess.s["allies"][0] == PUDGE
    t.handle(payload("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "dire", hero=PUDGE), sess.s)
    assert sess.s["phase"] == "game" and sess.s["allies"].count(PUDGE) == 1
    t.handle(payload("DOTA_GAMERULES_STATE_POST_GAME", "dire", hero=PUDGE), sess.s)
    assert sess.s["phase"] == "idle"


def test_new_match_resets_draft_but_not_on_repeats():
    sess = Session()
    sess.s.update(allies=[AM, None, None, None, None], bans=[AXE])
    t = gsi.Tracker(sess.apply)
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", match="1"), sess.s)
    assert sess.s["allies"] == [None] * 5 and sess.s["bans"] == []
    sess.s["allies"][1] = LION  # user typed a hero during the same match
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", match="1"), sess.s)
    assert sess.s["allies"][1] == LION
    assert t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", match="1"), sess.s) is None  # nothing new


def test_spectator_style_draft_block_fills_teams_from_my_side():
    sess = Session()
    t = gsi.Tracker(sess.apply)
    draft = {"activeteam": 2, "team2": {"pick0_id": AM, "pick1_class": "npc_dota_hero_pudge", "ban0_id": AXE},
             "team3": {"pick0_id": LION}}
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", team="dire", draft=draft), sess.s)
    assert sess.s["allies"][:1] == [LION] and sess.s["enemies"][:2] == [AM, PUDGE] and sess.s["bans"] == [AXE]
    assert t.status()["has_draft_block"]


def test_a_draft_block_of_my_team_only_keeps_the_enemies_read_from_the_screen():
    """A player's GSI draft block holds their own team: it must not clear the enemies the screen
    reader put on the board (that made the reader stop for good)."""
    sess = Session()
    sess.s.update(side="radiant", enemies=[LION, AXE, None, None, None])
    t = gsi.Tracker(sess.apply)
    t.match_id = "777"                       # the same match: no new-match reset
    own = {"team2": {"pick0_id": AM, "pick1_id": PUDGE}, "team3": {}}
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", team="radiant", draft=own), sess.s)
    assert sess.s["allies"][:2] == [AM, PUDGE] and sess.s["enemies"][:2] == [LION, AXE]
    # the same block again: nothing changes, nothing is sent
    assert "enemies" not in (t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", team="radiant", draft=own), sess.s) or {})


def test_merge_slots():
    assert gsi.merge_slots([None, LION, None, None, None], [AM, LION], {AM, LION}) == [AM, LION, None, None, None]
    assert gsi.merge_slots([AXE, None, None, None, None], [], {LION}) == [AXE, None, None, None, None]
    # a hero Dota puts in the other team leaves this one
    assert gsi.merge_slots([AXE, PUDGE, None, None, None], [AM], {AM, PUDGE}) == [AXE, AM, None, None, None]


def test_cfg_is_valid_keyvalues_with_token():
    d = kv.loads(gsi.cfg_text(12345))["Dota Drafter"]
    assert d["uri"] == "http://127.0.0.1:12345/" and d["data"]["draft"] == "1" and len(d["auth"]["token"]) == 32


def test_http_receiver_checks_token():
    got = []
    server = gsi.serve(got.append, port=0)
    port = server.server_address[1]
    try:
        def post(body):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/", data=json.dumps(body).encode(), method="POST")
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code
        assert post({"map": {}, "auth": {"token": "wrong"}}) == 401
        assert post({"map": {"game_state": "x"}, "auth": {"token": gsi._token()}}) == 200
        assert got and got[0]["map"]["game_state"] == "x"
    finally:
        server.shutdown()


def test_session_patch_moves_hero_instead_of_failing(monkeypatch):
    from drafter.api import session
    session.put(session.Session(allies=[None] * 5, enemies=[AM, None, None, None, None]))
    s = session.patch("gsi", allies=[AM, None, None, None, None])  # screen reading corrected the side
    assert s.allies[0] == AM and AM not in s.enemies


def test_log_keeps_a_week_and_stops_a_huge_day(tmp_path, monkeypatch):
    monkeypatch.setattr(gsi, "LOG_DIR", tmp_path)
    for d in range(1, 11):
        (tmp_path / f"2026-01-{d:02d}.jsonl").write_text("x\n")
    log = gsi._Log()
    log.write({"auth": {"token": "secret"}, "map": {"clock_time": 1}})
    days = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert len(days) == gsi.LOG_DAYS and "2026-01-01.jsonl" not in days
    today = tmp_path / days[-1]
    assert "secret" not in today.read_text()
    monkeypatch.setattr(gsi, "LOG_DAY_MAX", 10)
    size = today.stat().st_size
    log.write({"map": {"clock_time": 2}})
    assert today.stat().st_size == size


def test_a_broken_token_file_is_replaced(tmp_path, monkeypatch):
    f = tmp_path / "gsi.json"
    f.write_text("")
    monkeypatch.setattr(gsi, "STATE_FILE", f)
    t = gsi._token()
    assert len(t) == 32 and gsi._token() == t


def test_a_hero_newer_than_our_constants_does_not_break_the_stream():
    from drafter.api import session
    session._state = session.Session()
    t = gsi.Tracker(lambda **c: session.patch("gsi", **c))
    t.handle(payload("DOTA_GAMERULES_STATE_HERO_SELECTION", hero=999), session.get().model_dump())
    s = session.get()
    assert s.phase == "draft" and s.side == "radiant" and s.my_hero is None
    session._state = session.Session()
