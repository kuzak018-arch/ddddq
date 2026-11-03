"""The reader takes back its own wrong pick, keeps a right hero in its slot, and GSI's first match id
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


def test_a_wrong_pick_the_screen_stops_showing_is_taken_back():
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft", "my_hero": None}
    frames = [res([W, None, None, None, None])] * 2 + [res([None] * 5)] * runner.DOUBT_FRAMES
    r = make(state, frames)
    for _ in range(2):
        step(r, state)
    assert state["allies"][0] == W
    for _ in range(runner.DOUBT_FRAMES - 1):
        step(r, state)
    assert state["allies"][0] == W            # a few unreadable frames are not enough
    step(r, state)
    assert state["allies"][0] is None


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
