"""«Найти игрока»: what the user typed becomes an account, both sites merge, a closed profile is told."""

import pytest

from drafter.data import players as P

ACC = 1477734386
STEAM64 = ACC + P.STEAM64_BASE


@pytest.mark.parametrize("text", [
    str(ACC), f" {ACC} ", str(STEAM64), f"[U:1:{ACC}]",
    f"https://steamcommunity.com/profiles/{STEAM64}/", f"https://www.dotabuff.com/players/{ACC}/matches",
    f"https://stratz.com/players/{ACC}", f"https://www.opendota.com/players/{ACC}/heroes",
    f"https://ru.dotabuff.com/players/{ACC}", "https://steamcommunity.com/id/kuzak/",
])
def test_every_way_to_name_a_player(text):
    assert P.parse_target(text, resolve=lambda name: ACC if name == "kuzak" else 0) == ACC


@pytest.mark.parametrize("text", ["", "abc", "https://example.com/players", "99999999999999999999"])
def test_nonsense_is_explained(text):
    with pytest.raises(P.PlayerError):
        P.parse_target(text, resolve=lambda name: ACC)


def test_merge_prefers_stratz_matches_and_opendota_record():
    od = {"found": True, "name": "kuz", "avatar": "https://avatars.steamstatic.com/a.jpg", "rank_tier": 54, "wins": 600,
          "losses": 500, "heroes": [{"hero": 55, "games": 300, "wins": 170}], "matches": [{"id": 1, "pos": None}]}
    sz = {"name": "kuz", "anonymous": False, "wins": 10, "games": 20, "matches": [{"id": 2, "pos": 2}]}
    out = P.merge(ACC, od, sz)
    assert out["winrate"] == pytest.approx(600 / 1100) and out["games"] == 1100
    assert out["matches"][0]["pos"] == 2 and not out["closed"]
    assert out["links"]["dotabuff"].endswith(str(ACC)) and out["links"]["steam"].endswith(str(STEAM64))
    only_stratz = P.merge(ACC, None, sz)
    assert only_stratz["games"] == 20 and only_stratz["winrate"] == 0.5


def test_a_closed_profile_says_there_is_no_data():
    out = P.merge(ACC, {"found": True, "name": "hidden", "rank_tier": 71, "wins": 0, "losses": 0, "heroes": [], "matches": []},
                  {"name": "hidden", "anonymous": True, "wins": 0, "games": 0, "matches": []})
    assert out["closed"] and "Общедоступные данные матчей" in out["closed_note"]
    assert out["rank_tier"] == 71 and out["winrate"] is None          # the medal is still there


def test_one_site_down_does_not_hide_the_other(monkeypatch):
    monkeypatch.setattr(P, "_cache", {})
    monkeypatch.setattr(P, "_opendota", lambda acc: {"found": True, "name": "kuz", "wins": 3, "losses": 1, "heroes": [], "matches": []})

    def broken(acc):
        raise RuntimeError("Stratz HTTP 429: too many")

    monkeypatch.setattr(P, "_stratz", broken)
    out = P.lookup(str(ACC))
    assert out["name"] == "kuz" and out["winrate"] == 0.75 and "лимит" in out["errors"][0]
    monkeypatch.setattr(P, "_opendota", lambda acc: pytest.fail("cached: no second request"))
    assert P.lookup(str(ACC))["name"] == "kuz"


def test_unknown_stratz_fields_are_dropped():
    sent = []

    class SZ:
        def q(self, query):
            sent.append(query)
            if "smurfFlag" in query:
                raise RuntimeError('Stratz: [{"message": "Cannot query field \\"smurfFlag\\" on type \\"SteamAccountType\\"."}]')
            return {"player": {"steamAccount": {"name": "x"}}}

    assert P.query_dropping_unknown(SZ(), P._Q_STRATZ % (ACC, 5, ACC))["player"]["steamAccount"]["name"] == "x"
    assert len(sent) == 2 and "smurfFlag" not in sent[1] and "seasonRank" in sent[1]

    class Other:
        def q(self, query):
            raise RuntimeError("Stratz HTTP 401")

    with pytest.raises(RuntimeError):
        P.query_dropping_unknown(Other(), P._Q_STRATZ % (ACC, 5, ACC))


def test_links_open_only_for_known_sites(monkeypatch):
    from fastapi.testclient import TestClient

    from drafter.api import app as api
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setenv("DRAFTER_NO_BUILD_LOAD", "1")
    with TestClient(api.app) as c:
        assert c.post("/open-url", json={"url": f"https://www.dotabuff.com/players/{ACC}"}).json()["opened"]
        assert c.post("/open-url", json={"url": "https://gridstudio.me/workshop"}).status_code == 200
        for bad in ("http://stratz.com/x", "https://evil.example/x", "file:///C:/Windows", "https://stratz.com.evil.io/"):
            assert c.post("/open-url", json={"url": bad}).status_code == 422
        assert c.get("/players/lookup", params={"q": "abc"}).status_code == 503   # no network in tests
