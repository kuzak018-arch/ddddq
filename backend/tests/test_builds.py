import pytest

from drafter.builds import counter, standard
from drafter.data import constants, stratz

HAVE_DATA = (constants.DIR / "hero_index.json").exists() and stratz.hero("LEGEND_ANCIENT", 4) is not None
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="нужны константы и данные Stratz")


@needs_data
def test_standard_build_shape():
    b = standard.build(4, 1, "LEGEND_ANCIENT")  # Bloodseeker pos 1
    assert b["matches"] > 1000
    for section in ("starting", "boots", "early", "core", "situational"):
        assert all(0 < x["share"] <= 1.0 for x in b[section]), section
    assert b["core"] and b["skills"] and len(b["talents"]) == 4
    assert all("?" not in o["name"] for t in b["talents"] for o in t["options"])
    minutes = [x["minute"] for x in b["core"]]
    assert minutes == sorted(minutes)


@needs_data
def test_counter_items_and_rare_on_hero():
    pl, riki, zeus, necro, lion = 12, 32, 22, 36, 26
    recs = counter.against([pl, riki, zeus, necro, lion], 1, hero_items={"black_king_bar": 0.8, "mjollnir": 0.5})
    keys = [r["item"] for r in recs]
    assert "black_king_bar" in keys and "mjollnir" in keys
    assert keys.index("mjollnir") < keys.index("bfury")      # bfury is rare on the hero -> pushed down
    sup = [r["item"] for r in counter.against([riki], 5)]
    assert "ward_sentry" in sup or "dust" in sup


@needs_data
def test_no_rules_fire_for_empty_draft():
    assert counter.against([], 1) == []


@needs_data
def test_support_build_not_empty_and_shares_capped():
    # regression: Stratz dropped rare per-minute rows without matchLimit, supports got empty cores
    b = standard.build(3, 4, "LEGEND_ANCIENT")  # Bane pos 4
    assert len(b["core"]) >= 3
    for section in ("starting", "boots", "early", "core", "situational"):
        assert all(x["share"] <= 1.0 for x in b[section])
    assert all(x["cost"] >= standard.SITUATIONAL_MIN_COST for x in b["situational"])
