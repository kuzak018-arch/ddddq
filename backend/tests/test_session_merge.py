from drafter.api.merge import merge

E5 = [None] * 5


def st(allies=E5, enemies=E5, bans=(), side=None, pos=None):
    return {"allies": list(allies), "enemies": list(enemies), "bans": list(bans), "side": side, "pos": pos, "comfort": None}


def test_both_sides_changes_are_kept():
    base = st()
    theirs = st(enemies=[2, None, None, None, None])          # the reader put Axe
    mine = st(allies=[1, None, None, None, None])             # meanwhile the user put Anti-Mage
    out = merge(base, mine, theirs)
    assert out["allies"][0] == 1 and out["enemies"][0] == 2


def test_the_window_clearing_a_slot_wins_and_untouched_slots_follow_theirs():
    base = st(enemies=[2, 3, None, None, None])
    theirs = st(enemies=[2, 3, 4, None, None], side="radiant")
    mine = st(enemies=[None, 3, None, None, None])
    out = merge(base, mine, theirs)
    assert out["enemies"] == [None, 3, 4, None, None] and out["side"] == "radiant"


def test_a_hero_twice_stays_where_the_window_put_it():
    base = st()
    theirs = st(enemies=[5, None, None, None, None])
    mine = st(allies=[None, 5, None, None, None])
    out = merge(base, mine, theirs)
    assert out["allies"][1] == 5 and 5 not in out["enemies"]


def test_bans_added_and_removed_on_both_sides():
    base = st(bans=[7, 8])
    theirs = st(bans=[7, 8, 9])
    mine = st(bans=[8, 10])
    assert merge(base, mine, theirs)["bans"] == [8, 9, 10]


def test_put_from_an_old_rev_keeps_the_readers_hero(monkeypatch):
    from drafter.api import session
    from drafter.data import constants
    if not (constants.DIR / "heroes.json").exists():
        return
    monkeypatch.setattr(session, "_state", session.Session())
    monkeypatch.setattr(session, "_history", {0: session._state})
    base = session.get().rev
    session.patch("vision", enemies=[2, None, None, None, None])           # the reader puts Axe
    mine = session.Session(allies=[1, None, None, None, None])           # the window adds Anti-Mage from rev `base`
    out = session.put_from(mine, base)
    assert out.allies[0] == 1 and out.enemies[0] == 2
