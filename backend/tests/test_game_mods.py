"""«Оформление игры»: VPK and Panorama writers, the menu pack, fonts, install and removal."""

import struct
from pathlib import Path

import pytest

from drafter.game_mods import fonts as F
from drafter.game_mods import install as I
from drafter.game_mods import menu as M
from drafter.game_mods import vpk as V

FIX = Path(__file__).parent / "fixtures" / "valve"
WEBM = b"\x1a\x45\xdf\xa3" + bytes(range(50))


# ---------- writers ----------------------------------------------------------------------------

@pytest.mark.parametrize("file,path,crc", [
    ("dashboard_page_credits.vxml_c", "panorama/layout/dashboard_page_credits.vxml_c", 1675273883),
    ("tooltip_spidergraph.vcss_c", "panorama/styles/tooltips/tooltip_spidergraph.vcss_c", 3187935984),
    ("pip-left.vsvg_c", "panorama/images/dpc/pip-left.vsvg_c", 0xE2E0A7CF),
])
def test_panorama_resources_are_byte_identical_to_valves(file, path, crc):
    valve = (FIX / file).read_bytes()
    assert V.panorama_resource(path, V.panorama_source(valve), source_crc=crc) == valve


def test_panorama_source_survives_and_wrong_kinds_are_refused():
    layout = "<root><Panel id=\"Ю\" /></root>"
    assert V.panorama_source(V.panorama_resource("panorama/layout/a.vxml_c", layout)) == layout
    with pytest.raises(ValueError):
        V.panorama_resource("panorama/images/a.vtex_c", "x")


def test_vpk_lists_checksums_and_hashes_its_files():
    import hashlib
    files = [("panorama/layout/a.vxml_c", b"\x01\x02\x03"), ("zxc/zxc.webm", b"\x07" * 1000), ("readme", b"\x09")]
    pack = V.build_vpk(files)
    version, read = V.read_vpk(pack)
    assert version == 2
    assert [(f.path, f.length, f.crc, f.data) for f in read] == [(p, len(d), V.crc32(d), d) for p, d in files]
    assert pack[-16:] == hashlib.md5(pack[:-16]).digest()
    assert pack[-32:-16] == hashlib.md5(b"").digest()
    with pytest.raises(ValueError):
        V.build_vpk([("../evil", b"x")])


# ---------- the menu pack ----------------------------------------------------------------------

def _files(pack):
    return {f.path: f.data for f in V.read_vpk(pack)[1]}


def test_menu_pack_points_valves_dashboard_at_our_video():
    files = _files(M.build_pack(WEBM, clean=True))
    assert sorted(files) == sorted([M.DASHBOARD, M.HOME, M.MENU_LAYOUT, M.MENU_STYLE, M.MENU_VIDEO])
    ours = V.panorama_source(files[M.DASHBOARD])
    valve = M.valve_layout("dashboard.xml")
    assert f'override-background="s2r://{M.MENU_LAYOUT}"' in ours
    import re
    strip = lambda t: re.sub(r'override-background="[^"]*"', "", t)  # noqa: E731
    assert strip(ours) == strip(valve)  # everything else of Valve's layout is kept
    assert f'src="s2r://{M.MENU_VIDEO}"' in V.panorama_source(files[M.MENU_LAYOUT])
    assert "TodayPages" not in V.panorama_source(files[M.HOME])
    assert files[M.MENU_VIDEO] == WEBM


def test_hero_and_grid_pages():
    files = _files(M.build_pack(WEBM, hero="own", hero_video=WEBM, grid="dim", grid_dim=0.4))
    hero = V.panorama_source(files[M.HERO_PAGE])
    assert f'src="s2r://{M.HERO_VIDEO}"' in hero and M.HERO_STYLE in hero
    assert "#00000066" in V.panorama_source(files[M.GRID_STYLE])  # 0.4 · 255 = 102
    assert "DrafterGridVeil" in V.panorama_source(files[M.GRID_PAGE])
    menu_hero = _files(M.build_pack(WEBM, hero="menu", grid="own", grid_video=WEBM))
    assert f'src="s2r://{M.MENU_VIDEO}"' in V.panorama_source(menu_hero[M.HERO_PAGE])
    assert 'hidebackground="true"' in V.panorama_source(menu_hero[M.GRID_PAGE])
    # only the pages, Valve's menu kept
    only = _files(M.build_pack(None, grid="dim"))
    assert sorted(only) == sorted([M.GRID_PAGE, M.GRID_STYLE])


def test_menu_pack_refuses_what_dota_would_not_load():
    with pytest.raises(M.PackError):
        M.build_pack(b"not webm")
    with pytest.raises(M.PackError):
        M.build_pack(None)
    with pytest.raises(M.PackError):
        M.build_pack(None, hero="menu")
    with pytest.raises(M.PackError):
        M._panorama("panorama/layout/x.vxml_c", '<root><Button onactivate="X()" /></root>')
    with pytest.raises(M.PackError):
        M._panorama("panorama/styles/x.vcss_c", "/* Ю */")


# ---------- fonts ------------------------------------------------------------------------------

def _name(table, nid):
    count, storage = struct.unpack_from(">HH", table, 2)
    for i in range(count):
        platform, _enc, _lang, rid, length, offset = struct.unpack_from(">HHHHHH", table, 6 + i * 12)
        if rid == nid and platform == 3:
            return table[storage + offset:storage + offset + length].decode("utf-16-be")
    return None


def test_font_pack_carries_valves_names_and_keeps_the_grid_font():
    faces = F.catalog_fonts("libre-franklin")
    assert not faces[0].missing()["cyrillic"]
    files = F.font_pack(faces, ["Radiance", "RadianceM", "Reaver"], keep=[F.GRID_FONT_FILE])
    assert len(files) == 28 and "radiance-semibold.otf" not in files
    face = F.read_font(files["reaver-bold.otf"])
    assert (face.names[1], face.names[2], face.names[6]) == ("Reaver", "Bold", "Reaver-Bold")
    assert face.weight == 700
    semibold = F.read_font(files["radiance-semibolditalic.otf"])
    assert _name(semibold.tables["name"], 16) == "Radiance" and semibold.italic
    # a checksum that sums to Valve's magic over the whole file
    assert F._checksum(files["reaver-bold.otf"]) == 0xB1B0AFBA
    assert len(F.font_pack(faces, ["Reaver"])) == 5


def test_fonts_the_game_cannot_read_are_refused():
    for data in (b"wOF2" + b"\0" * 20, b"ttcf" + b"\0" * 20, b"hello world!!"):
        with pytest.raises(F.FontError):
            F.read_font(data)


def test_catalog_has_cyrillic_ofl_fonts():
    fonts = F.catalog()
    assert len(fonts) >= 8 and all("OFL" in f["license"] or "Open Font" in f["license"] for f in fonts)
    for f in fonts:
        assert (F.catalog_dir() / f["id"] / "OFL.txt").exists()


# ---------- install and removal ----------------------------------------------------------------

@pytest.fixture
def dota(tmp_path, monkeypatch):
    root = tmp_path / "dota 2 beta"
    (root / "game" / "dota" / "cfg").mkdir(parents=True)
    fonts = root / "game" / "dota" / "panorama" / "fonts"
    fonts.mkdir(parents=True)
    for name in F.DOTA_FONT_FILES:
        (fonts / name).write_bytes(b"VALVE " + name.encode())
    (root / "game" / "dota" / "cfg" / "boot.vcfg").write_text('"boot"\n{\n\t"AudioLanguage"\t\t"russian"\n}\n')
    monkeypatch.setattr(I.dota_paths, "dota_path", lambda: root)
    monkeypatch.setattr(I.dota_paths, "steam_path", lambda: None)
    state = {"running": False}
    monkeypatch.setattr(I.hero_grid, "dota_running", lambda: state["running"])
    monkeypatch.setattr(I.config, "DATA", tmp_path / "data")
    monkeypatch.setenv("TEMP", str(tmp_path / "temp"))
    return root, state


def test_language_comes_from_boot_vcfg(dota):
    root, _ = dota
    assert I.voice_language(root, None) == ("russian", "настройки Доты (boot.vcfg)")
    (root / "game" / "dota" / "cfg" / "boot.vcfg").write_text('"boot" { }')
    assert I.voice_language(root, None)[0] == "english"


def test_background_goes_into_the_language_folder_and_comes_out(dota):
    root, state = dota
    pack = M.build_pack(WEBM)
    res = I.install_background(None, pack, {"label": "x"})
    target = root / "game" / "dota_russian" / "pak02_dir.vpk"
    assert Path(res["path"]) == target and target.read_bytes() == pack
    st = I.status(None)
    assert st["usable"] and st["background_intact"] and st["language"] == "russian"
    state["running"] = True
    with pytest.raises(I.ModError):
        I.remove_background()
    state["running"] = False
    assert I.remove_background() and not target.exists()


def test_someone_elses_pak02_is_kept_and_put_back(dota):
    root, _ = dota
    folder = root / "game" / "dota_russian"
    folder.mkdir(parents=True)
    (folder / "pak02_dir.vpk").write_bytes(b"GRIDSTUDIO")
    res = I.install_background(None, M.build_pack(WEBM), {})
    assert Path(res["path"]).name == "pak03_dir.vpk"  # a free number, theirs untouched
    assert (folder / "pak02_dir.vpk").read_bytes() == b"GRIDSTUDIO"
    assert I.status(None)["other_packs"] == ["pak02_dir.vpk"]
    I.remove_background()
    assert (folder / "pak02_dir.vpk").read_bytes() == b"GRIDSTUDIO" and not (folder / "pak03_dir.vpk").exists()


def test_english_voice_is_explained_not_changed(dota):
    root, _ = dota
    boot = root / "game" / "dota" / "cfg" / "boot.vcfg"
    boot.write_text('"boot"\n{\n\t"AudioLanguage"\t\t"english"\n}\n')
    with pytest.raises(I.ModError, match="озвучки"):
        I.install_background(None, M.build_pack(WEBM), {})
    assert "english" in boot.read_text()  # Dota's settings untouched


def test_fonts_replace_valves_files_with_a_backup_and_come_back(dota):
    root, state = dota
    fonts = root / "game" / "dota" / "panorama" / "fonts"
    (Path(I.os.environ["TEMP"]) / "fontconfig").mkdir(parents=True)
    files = F.font_pack(F.catalog_fonts("oswald"), ["Reaver"])
    I.install_fonts(files, {"font": "oswald"})
    assert (fonts / "reaver-bold.otf").read_bytes() == files["reaver-bold.otf"]
    assert not (Path(I.os.environ["TEMP"]) / "fontconfig").exists()  # fontconfig's cache cleared
    assert I.status(None)["fonts_intact"]
    # a second font for Radiance only: Reaver gets Valve's back
    files2 = F.font_pack(F.catalog_fonts("audex"), ["Radiance"])
    I.install_fonts(files2, {"font": "audex"})
    assert (fonts / "reaver-bold.otf").read_bytes() == b"VALVE reaver-bold.otf"
    assert I.remove_all() == {"background": False, "fonts": True}
    for name in F.DOTA_FONT_FILES:
        assert (fonts / name).read_bytes() == b"VALVE " + name.encode()


def test_api_bundle_install_and_remove(dota, monkeypatch):
    from fastapi.testclient import TestClient
    from drafter.api import app as api
    client = TestClient(api.app)
    meta = b'{"accept": true, "has_menu": true, "clean": true, "hero": "menu", "grid": "dim", "grid_dim": 0.3}'
    body = struct.pack("<I", len(meta)) + meta + struct.pack("<I", len(WEBM)) + WEBM
    r = client.post("/game-mods/background", content=body)
    assert r.status_code == 200, r.text
    assert client.get("/game-mods/status").json()["background"]["hero"] == "menu"
    no = b'{"has_menu": true}'
    assert client.post("/game-mods/background", content=struct.pack("<I", len(no)) + no).status_code == 422
    fm = b'{"accept": true, "catalog": "audex", "families": ["Radiance"], "keep_grid": true}'
    r = client.post("/game-mods/fonts", content=struct.pack("<I", len(fm)) + fm)
    assert r.status_code == 200 and r.json()["files"] == 11
    assert client.post("/game-mods/remove", json={"what": "all"}).json()["removed"] == {"background": True, "fonts": True}
