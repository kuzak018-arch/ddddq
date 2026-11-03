import json

import httpx
import pytest

from drafter.data import steam_guides as G

GUIDE = r'''
// written by the in-game guide editor
"guidedata"
{
	"Hero"		"npc_dota_hero_antimage"
	"Title"		"Anti-Mage: \"farm\" and split push"
	"ItemBuild"
	{
		"Items"
		{
			"#DOTA_Item_Build_Starting_Items"
			{
				"item"		"item_tango"
				"item"		"item_quelling_blade"
				"item"		"item_branches"
			}
			"#DOTA_Item_Build_Core_Items"	{ "item" "item_bfury" "item" "item_manta" }
			"Против магов"
			{
				"item"		"item_black_king_bar"
			}
			"#DOTA_Item_Build_Empty" { }
		}
	}
	"AbilityBuild"
	{
		"AbilityOrder"
		{
			"2"		"antimage_blink"
			"1"		"antimage_mana_break"
			"10"	"special_bonus_unique_antimage"
			"3"		"antimage_counterspell"   [$WIN32]
		}
	}
}
'''


def test_parse_kv_keeps_repeats_and_skips_comments():
    kv = G.parse_kv(GUIDE)
    starting = kv["guidedata"]["ItemBuild"]["Items"]["#DOTA_Item_Build_Starting_Items"]["item"]
    assert starting == ["item_tango", "item_quelling_blade", "item_branches"]
    assert kv["guidedata"]["Title"] == 'Anti-Mage: "farm" and split push'


def test_guide_from_kv():
    g = G.guide_from_kv(G.parse_kv(GUIDE))
    assert g["hero"] == "antimage" and g["title"].startswith("Anti-Mage")
    assert g["items"] == [{"name": "Старт", "items": ["tango", "quelling_blade", "branches"]},
                          {"name": "Основные", "items": ["bfury", "manta"]},
                          {"name": "Против магов", "items": ["black_king_bar"]}]
    assert g["abilities"] == ["antimage_mana_break", "antimage_blink", "antimage_counterspell", "special_bonus_unique_antimage"]
    assert G.guide_from_kv(G.parse_kv('"x" { "a" "b" }')) is None
    assert G.guide_from_kv(G.parse_kv('"g" { "Hero" "npc_dota_hero_axe" }')) is None  # no build: not a guide


def _client(files: list[dict], bodies: dict[str, str], calls: list):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url)
        if "QueryFiles" in req.url.path:
            assert req.url.params["key"] == "K" * 32 and req.url.params["appid"] == "570"
            return httpx.Response(200, json={"response": {"publishedfiledetails": files}})
        if "GetPlayerSummaries" in req.url.path:
            return httpx.Response(200, json={"response": {"players": [{"steamid": "765", "personaname": "Автор"}]}})
        if str(req.url) in bodies:
            return httpx.Response(200, text=bodies[str(req.url)])
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("STEAM_API_KEY", "K" * 32)
    monkeypatch.setattr(G, "DIR", tmp_path)
    monkeypatch.setattr(G.constants, "hero_by_id", lambda: {1: {"key": "antimage", "name": "Anti-Mage"}})
    monkeypatch.setattr(G.constants, "current_patch", lambda: {"name": "7.41", "ts": 1_000})
    monkeypatch.setattr(G.constants, "_load", lambda name: {"bfury": {"dname": "Battle Fury"}})
    return tmp_path


def test_search_ranks_fresh_and_voted_and_drops_other_heroes(env):
    axe = GUIDE.replace("npc_dota_hero_antimage", "npc_dota_hero_axe")
    files = [
        {"publishedfileid": "1", "result": 1, "file_url": "https://cdn/1", "creator": "765", "time_updated": 500,
         "vote_data": {"votes_up": 5000, "votes_down": 10}, "subscriptions": 90000},          # old patch
        {"publishedfileid": "2", "result": 1, "file_url": "https://cdn/2", "creator": "765", "time_updated": 2000,
         "vote_data": {"votes_up": 50, "votes_down": 5}, "subscriptions": 300},
        {"publishedfileid": "3", "result": 1, "file_url": "https://cdn/3", "time_updated": 3000,
         "vote_data": {"votes_up": 900, "votes_down": 5}},                                     # another hero
        {"publishedfileid": "4", "result": 1, "file_url": "https://cdn/4", "time_updated": 3000},  # not a guide
        {"publishedfileid": "5", "result": 1, "time_updated": 3000},                           # no file
    ]
    calls = []
    http = _client(files, {"https://cdn/1": GUIDE, "https://cdn/2": GUIDE, "https://cdn/3": axe, "https://cdn/4": "junk"}, calls)
    out = G.for_hero(1, http=http, now=10_000)
    assert out["status"] == "ok"
    assert [g["id"] for g in out["guides"]] == ["2", "1"]  # the fresh one first, then the old popular one
    g = out["guides"][0]
    assert g["author"] == "Автор" and g["votes_up"] == 50 and g["url"].endswith("?id=2")
    assert g["items"][0]["items"] == ["tango", "quelling_blade", "branches"]
    assert out["item_names"]["bfury"] == "Battle Fury" and out["item_names"]["tango"] == "tango"
    n = len(calls)
    assert G.for_hero(1, http=http, now=10_000 + 3600)["guides"][0]["id"] == "2"  # cached for a day
    assert len(calls) == n


def test_no_key_and_errors(env, monkeypatch):
    monkeypatch.setenv("STEAM_API_KEY", "")
    assert G.for_hero(1)["status"] == "no_key"
    monkeypatch.setenv("STEAM_API_KEY", "K" * 32)
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    out = G.for_hero(1, http=bad, now=1)
    assert out["status"] == "error" and "ключ" in out["error"]
    assert json.loads((env / "1.json").read_text(encoding="utf-8"))["status"] == "error"


def test_a_guide_without_file_url_is_fetched_by_its_content_handle(env):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if "QueryFiles" in req.url.path:
            ft = req.url.params["filetype"]
            files = [{"publishedfileid": "7", "result": 1, "hcontent_file": "555", "time_updated": 3000}] if ft == "20" else []
            return httpx.Response(200, json={"response": {"publishedfiledetails": files}})
        if "GetUGCFileDetails" in req.url.path:
            assert req.url.params["ugcid"] == "555"
            return httpx.Response(200, json={"data": {"url": "https://ugc/7"}})
        if str(req.url) == "https://ugc/7":
            return httpx.Response(200, text=GUIDE)
        return httpx.Response(200, json={"response": {"players": []}})
    out = G.for_hero(1, http=httpx.Client(transport=httpx.MockTransport(handler)), now=50_000)
    assert [g["id"] for g in out["guides"]] == ["7"]
    assert out["diag"] == {"queried": 1, "with_file": 1, "downloaded": 1, "guides": 1, "this_hero": 1, "kinds": {"text": 1}}


def test_an_old_cache_is_asked_again(env):
    (env / "1.json").write_text(json.dumps({"status": "ok", "guides": [], "fetched": 9_999_999_999}), encoding="utf-8")
    hits = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: hits.append(1) or httpx.Response(200, json={"response": {}})))
    G.for_hero(1, http=http, now=10_000)
    assert hits         # the old cache (no version) is not trusted


def test_decode_binary_json_and_zip():
    import io
    import zipfile

    def kv_bin(d):
        out = b""
        for k, v in d.items():
            if isinstance(v, dict):
                out += b"\x00" + k.encode() + b"\x00" + kv_bin(v) + b"\x08"
            else:
                out += b"\x01" + k.encode() + b"\x00" + v.encode() + b"\x00"
        return out
    tree = {"guidedata": {"Hero": "npc_dota_hero_antimage", "Items": {"#DOTA_Item_Build_Core_Items": {"item": "item_bfury"}}}}
    kind, t = G.decode_file(kv_bin(tree) + b"\x08")
    assert kind == "binary" and G.guide_from_kv(t)["items"] == [{"name": "Основные", "items": ["bfury"]}]
    kind, t = G.decode_file(json.dumps(tree).encode())
    assert kind == "json" and G.guide_from_kv(t)["hero"] == "antimage"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("guide.txt", GUIDE)
    kind, t = G.decode_file(buf.getvalue())
    assert kind == "zip/text" and G.guide_from_kv(t)["hero"] == "antimage"
    assert G.decode_file(b"\x89PNG\r\n\x1a\nxxxx")[0] == "image"
