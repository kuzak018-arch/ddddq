"""After a match: the breakdown by itself, the user's rating kept."""

import pytest

from drafter import after_match, ruin
from drafter.data import constants
from tests.test_ruin import HEROES, match

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists(), reason="нужны константы героев")


def test_the_end_of_a_match_starts_the_follow_up_once(monkeypatch):
    started = []
    a = after_match.AfterMatch(publish=lambda *x, **k: None)
    monkeypatch.setattr(a, "follow", lambda mid, hero: started.append((mid, hero)))
    monkeypatch.setattr(after_match.threading, "Thread", lambda target, args, **k: type("T", (), {"start": lambda self: target(*args)})())
    assert not a.on_state("DOTA_GAMERULES_STATE_HERO_SELECTION", "DOTA_GAMERULES_STATE_STRATEGY_TIME", "7", 1)
    assert a.on_state("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "DOTA_GAMERULES_STATE_POST_GAME", "7", 1)
    assert started == [(7, 1)]


def test_follow_waits_for_the_match_then_for_the_parse_and_records_my_rating(tmp_path, monkeypatch):
    monkeypatch.setattr(after_match, "PATH", tmp_path / "mine.json")
    raw_unparsed = match(radiant_win=False, bad=1)
    raw_unparsed["opendota"]["version"] = None
    raw_parsed = match(radiant_win=False, bad=1)
    answers = [ruin.RuinError("нет"), raw_unparsed, raw_parsed]
    monkeypatch.setattr(ruin, "fetch", lambda mid, refresh=False: (lambda a: (_ for _ in ()).throw(a) if isinstance(a, Exception) else a)(answers.pop(0)))
    events = []
    clock = [0.0]
    a = after_match.AfterMatch(publish=lambda kind, **d: events.append((kind, d)), account_id=lambda: None,
                               sleep=lambda s: clock.__setitem__(0, clock[0] + s), now=lambda: clock[0])
    a.follow(1, HEROES[1])
    assert [e[1]["parsed"] for e in events] == [False, True]
    hist = after_match.history()
    assert len(hist) == 1 and hist[0]["hero"] == HEROES[1] and hist[0]["tag"] == "ruiner" and hist[0]["parsed"]
