"""The overlay's game plan: timing windows, style tips, how to finish, who to kill."""

import polars as pl
import pytest

from drafter import gameplan
from drafter.data import constants
from drafter.model import timing

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists(), reason="нужны константы героев")

AM, AXE, LICH, CM, PUDGE, SPECTRE, MEDUSA, BROOD, TINY, ZEUS = 1, 2, 31, 5, 14, 67, 94, 61, 19, 22


def frame():
    """Early heroes (Broodmother, Tiny) win short games, late ones (Spectre, Medusa) long ones."""
    rows = []
    for i in range(400):
        short = i % 2 == 0
        rows.append({"duration": (20 if short else 55) * 60, "radiant_team": [BROOD, TINY, AXE], "dire_team": [SPECTRE, MEDUSA, LICH],
                     "radiant_win": short if i % 10 else not short})
    return pl.DataFrame(rows)


def test_timing_curves_from_the_match_base():
    t = timing.build(frame())
    brood, spectre = t["heroes"][str(BROOD)]["wr"], t["heroes"][str(SPECTRE)]["wr"]
    assert brood[0] > 0.7 and brood[-1] < 0.3 and spectre[-1] > 0.7 and t["base"][0] == 0.5


def test_an_early_draft_is_told_to_finish_fast():
    t = timing.build(frame())
    out = gameplan.plan([BROOD, TINY, AXE], [SPECTRE, MEDUSA, LICH], minute=50, t=t)
    texts = [x["text"] for x in out["tips"]]
    assert out["shape"] == "early" and texts[0].startswith("Ваше окно") and "Medusa" in texts[0]
    assert any(x["kind"] == "now" and "время врагов" in x["text"] for x in out["tips"])
    assert out["tips"][-1]["kind"] == "finish"


def test_without_a_match_base_the_plan_still_has_tips():
    out = gameplan.plan([AXE, LICH], [AM, PUDGE], t={})
    assert out["timing"] is None and out["tips"][-1]["kind"] == "finish"


def test_who_to_kill_uses_the_matchup_and_how_fragile_the_hero_is():
    counter = lambda a, b: {CM: 0.2, AXE: -0.2}.get(b, 0.0)   # noqa: E731 — I counter CM, Axe counters me
    out = gameplan.killable(PUDGE, [CM, AXE, AM], counter, minute=12, t={})
    by = {x["hero"]: x for x in out}
    assert by[CM]["verdict"] == "kill" and by[AXE]["verdict"] == "avoid"
    assert any("контришь" in r for r in by[CM]["reasons"]) and "есть побег" in by[AM]["reasons"]
