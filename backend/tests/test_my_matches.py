"""How a match is judged: label from IMP and the result, reasons from the norm, the summary."""

from drafter.data import my_matches as mm

ME = 1477734386


def rec(match_id, win, imp, *, nw=15000, norm_nw=15000, deaths=5, norm_deaths=5.0, cs10=40, norm_cs10=40,
        lane="SAFE_LANE", radiant=True, lanes=None, parsed=True, team=None, start=0):
    return {
        "id": match_id, "start": start, "duration": 31 * 60, "radiant_win": win == radiant, "parsed": parsed,
        "lanes": lanes or {"top": "TIE", "mid": "TIE", "bot": "TIE"},
        "me": {"hero": 4, "radiant": radiant, "win": win, "pos": 1, "lane": lane, "k": 6, "d": deaths, "a": 6,
               "lh": 230, "dn": 10, "gpm": 465, "xpm": 560, "nw": nw, "hd": 18000, "td": 1800, "imp": imp,
               "award": None, "cs10": cs10, "nw10": 3400},
        "norm": {"t": 31, "nw": norm_nw, "xp": 17360, "kills": 7, "deaths": norm_deaths, "assists": 7,
                 "hd": 18000, "td": 1800, "cs10": norm_cs10, "nw10": 3400},
        "team": team,
    }


def test_labels_follow_result_and_imp():
    cases = [(True, 25, "carried"), (True, 0, "won_together"), (True, -20, "team_carried"),
             (False, 15, "lost_played_well"), (False, 3, "lost_together"), (False, -30, "threw")]
    for win, imp, key in cases:
        assert mm.assess(rec(1, win, imp))["label_key"] == key


def test_reasons_carry_numbers_in_the_labels_direction():
    bad = mm.assess(rec(1, False, -30, nw=11000, norm_nw=15000, deaths=11, norm_deaths=4.5,
                        lanes={"top": "TIE", "mid": "TIE", "bot": "DIRE_STOMP"}))
    assert bad["label"] == "слил игру я"
    text = " ".join(bad["reasons"])
    # the two worst deviations win: 11 deaths against 4.5 and a stomped lane outweigh -27% networth
    assert "IMP -30" in text and "смертей 11 при норме 4.5" in text and "линия проиграна с разгромом" in text
    assert bad["metrics"]["nw"] == round((11000 / 15000 - 1) * mm.WEIGHTS["nw"], 3)
    only_nw = mm.assess(rec(5, False, -30, nw=11000, norm_nw=15000))
    assert any("нетворс 11k при норме 15k к 31-й минуте (-27%)" == r for r in only_nw["reasons"])
    good = mm.assess(rec(2, True, 30, nw=19000, norm_nw=15000, cs10=60, norm_cs10=40))
    assert any("+27%" in r for r in good["reasons"]) and any("+50%" in r for r in good["reasons"])


def test_lane_side_and_team_context():
    team = [{"acc": ME, "hero": 4, "radiant": False, "pos": 1, "nw": 15000, "imp": 20}] + \
           [{"acc": i, "hero": 10 + i, "radiant": False, "pos": 2 + i % 4, "nw": 9000 + i, "imp": -25} for i in range(4)] + \
           [{"acc": 100 + i, "hero": 20 + i, "radiant": True, "pos": 1 + i, "nw": 12000, "imp": 10} for i in range(5)]
    r = rec(3, False, 20, radiant=False, lane="SAFE_LANE", lanes={"top": "DIRE_VICTORY", "mid": "TIE", "bot": "TIE"}, team=team)
    a = mm.assess(r)
    assert mm.lane_result(r) == "won"               # Dire's safe lane is the top one
    assert a["nw_place"] == 1 and a["team_imp"] == -25
    assert a["label"] == "проиграл, хотя сыграл хорошо" and any("остальных в команде -25" in x for x in a["reasons"])


def test_unparsed_match_waits(monkeypatch):
    assert "pending" in mm.assess(rec(4, True, None, parsed=False))


def test_summary_splits_losses(monkeypatch, tmp_path):
    data = {"fetched": 1, "matches": {str(i): r for i, r in enumerate([
        rec(1, False, -30, start=5), rec(2, False, 20, start=4), rec(3, False, 0, start=3),
        rec(4, True, 30, start=2), rec(5, True, None, parsed=False, start=1)])}}
    monkeypatch.setattr(mm, "load", lambda: data)
    h = mm.history()
    s = h["summary"]
    assert (s["losses"], s["losses_me"], s["losses_team"], s["losses_together"]) == (3, 1, 1, 1)
    assert (s["wins"], s["wins_me"], s["pending"]) == (1, 1, 1)
    assert [m["id"] for m in h["matches"]] == [1, 2, 3, 4, 5]     # newest first


def team_of(my_imp, mates_imp, radiant=True):
    return [{"acc": ME, "hero": 4, "radiant": radiant, "pos": 1, "nw": 15000, "imp": my_imp}] + \
           [{"acc": i, "hero": 10 + i, "radiant": radiant, "pos": 2 + i, "nw": 9000, "imp": mates_imp} for i in range(4)]


def test_blame_is_relative_to_the_team():
    # everyone played badly: not "I threw", a loss together
    assert mm.assess(rec(1, False, -48, team=team_of(-48, -42)))["label_key"] == "lost_together"
    # the rest did clearly better: on me
    assert mm.assess(rec(2, False, -30, team=team_of(-30, 5)))["label_key"] == "threw"
    # I was good and so was everyone: a win together, not "carried"
    assert mm.assess(rec(3, True, 25, team=team_of(25, 20)))["label_key"] == "won_together"
    assert mm.assess(rec(4, True, 25, team=team_of(25, -5)))["label_key"] == "carried"
