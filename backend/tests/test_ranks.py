"""Points to the next star and medal from a rank tier (and OpenDota's estimate when it fits)."""

from drafter.data import ranks


def test_legend_4_window_and_steps_without_an_estimate():
    p = ranks.progress(54)
    assert (p["low"], p["high"]) == (3542, 3695) and p["name"] == "Legend 4" and not p["from_estimate"]
    assert p["mmr"] == 3619                                   # the middle of the star
    assert p["next_star"]["name"] == "Legend 5" and p["next_star"]["points"] == 77
    assert p["next_rank"]["name"] == "Ancient 1" and p["next_rank"]["points"] == 231
    assert p["next_rank"]["games"] == 10                      # 231 / 25, rounded up


def test_the_estimate_is_used_only_when_it_falls_into_the_star():
    inside = ranks.progress(54, 3600)
    assert inside["from_estimate"] and inside["mmr"] == 3600 and inside["next_star"]["points"] == 96
    outside = ranks.progress(54, 2100)                        # an old estimate unrelated to the rank
    assert not outside["from_estimate"] and outside["mmr"] == 3619


def test_the_last_star_goes_straight_to_the_next_medal():
    p = ranks.progress(65)
    assert p["name"] == "Ancient 5" and p["next_star"] is None and p["next_rank"]["name"] == "Divine 1"
    assert p["low"] == 4466 and p["high"] == 4619


def test_divine_stars_are_wider_and_lead_to_immortal():
    p = ranks.progress(75)
    assert (p["low"], p["high"]) == (5260, 5419) and p["next_rank"]["name"] == "Immortal"
    assert p["next_rank"]["points"] == 80


def test_the_first_rank_and_no_rank():
    assert ranks.progress(11)["low"] == 0 and ranks.progress(11)["next_star"]["name"] == "Herald 2"
    assert ranks.progress(None) is None and ranks.progress(0) is None


def test_immortals_and_odd_tiers_have_no_progress():
    for tier in (80, 81, 56, 5, 100):
        assert ranks.progress(tier) is None
