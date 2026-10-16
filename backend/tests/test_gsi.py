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
