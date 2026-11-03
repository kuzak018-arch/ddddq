"""The reader keeps a placed hero, replaces it only with another hero it reads in that slot, keeps a right hero in its slot, and GSI's first match id
in a running draft doesn't wipe the board."""

from drafter import gsi
from drafter.vision import matcher, runner

S = matcher.SlotResult
A, B, W = 1, 2, 3


def res(radiant, dire=None):
    fill = lambda xs: [S(h, 0.9, 0.2, [(h, 0.9)]) if h else S(None, 0.3, 0.0, [(77, 0.3), (78, 0.2)]) for h in xs]  # noqa: E731
    return {"radiant": fill(radiant), "dire": fill(dire or [None] * 5), "bans": [], "warnings": [], "source": "bars"}


def make(state, frames):
    r = runner.Runner(lambda: state, lambda **c: state.update(c), lambda d: None)
    r.cautious = False
    seq = iter(frames)
    r._read = lambda frame: next(seq)
    return r


def step(r, state):
    r.step(None, dict(state, allies=list(state["allies"]), enemies=list(state["enemies"])))


def test_a_placed_hero_stays_when_the_screen_stops_showing_it():
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft", "my_hero": None}
    frames = [res([W, None, None, None, None])] * 2 + [res([None] * 5)] * 30
    r = make(state, frames)
    for _ in range(32):
        step(r, state)
    assert state["allies"][0] == W            # unreadable frames never empty a slot


def test_a_wrong_pick_is_replaced_by_the_hero_the_slot_shows():
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft", "my_hero": None}
    need = runner.STABLE_FRAMES + runner.CORRECT_EXTRA
    frames = [res([W, None, None, None, None])] * 2 + [res([B, None, None, None, None])] * need
    r = make(state, frames)
    for _ in range(2):
        step(r, state)
    assert state["allies"][0] == W
    for _ in range(need - 1):
        step(r, state)
    assert state["allies"][0] == W            # one or two frames of another hero are not enough
    step(r, state)
    assert state["allies"][0] == B


def test_a_right_hero_is_not_pulled_out_by_a_look_alike():
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft", "my_hero": None}
    look = res([A, None, A, None, None])
    look["radiant"][2] = S(A, 0.95, 0.2, [(A, 0.95)])      # the look-alike scores higher, so unique() keeps slot 2
    frames = [res([A, None, None, None, None])] * 2 + [look] * 5
    r = make(state, frames)
    for _ in range(7):
        step(r, state)
    assert state["allies"][0] == A and state["allies"].count(A) == 1


def test_first_match_id_in_a_running_draft_keeps_the_board():
    t = gsi.Tracker(lambda **c: None)
    cur = {"phase": "draft", "allies": [A, B, None, None, None], "enemies": [None] * 5, "bans": [], "side": "radiant"}
    msg = lambda mid: {"map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION", "matchid": mid}, "player": {"team_name": "radiant"}}  # noqa: E731
    assert not (t.handle(msg("0"), cur) or {}).get("allies")
    assert "allies" not in (t.handle(msg("123"), cur) or {})
    # a really new match afterwards: the board starts empty
    assert (t.handle(msg("456"), cur) or {}).get("allies") == [None] * 5
