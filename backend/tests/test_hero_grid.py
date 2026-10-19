import copy
import json
import os
from pathlib import Path

import pytest

from drafter import hero_grid as hg
from drafter.data import constants
from drafter.model import grids

# A file the way the game writes it: tabs, six decimals, brackets on their own line, no final newline.
USER_FILE = (
    '{\n\t"version": 3,\n\t"configs":\n\t[\n\t\t{\n\t\t\t"config_name": "Моя сетка",\n\t\t\t"categories":\n\t\t\t[\n'
    '\t\t\t\t{\n\t\t\t\t\t"category_name": "Керри",\n\t\t\t\t\t"x_position": 87.038605,\n\t\t\t\t\t"y_position": 79.680527,\n'
    '\t\t\t\t\t"width": 334.265717,\n\t\t\t\t\t"height": 94.449905,\n\t\t\t\t\t"hero_ids":\n\t\t\t\t\t[\n'
    '\t\t\t\t\t\t4,\n\t\t\t\t\t\t1\n\t\t\t\t\t]\n\t\t\t\t},\n'
    '\t\t\t\t{\n\t\t\t\t\t"category_name": "-",\n\t\t\t\t\t"x_position": 605.611755,\n\t\t\t\t\t"y_position": 146.842804,\n'
    '\t\t\t\t\t"width": 30.000000,\n\t\t\t\t\t"height": 30.000000,\n\t\t\t\t\t"hero_ids":\n\t\t\t\t\t[\n\t\t\t\t\t]\n\t\t\t\t}\n'
    '\t\t\t]\n\t\t}\n\t]\n}'
)


def cfg(name="Драфтер · Мета", heroes=(1, 2, 3)):
    return {"config_name": name, "categories": [{"category_name": "Тир S", "x_position": 16.0, "y_position": 16.0,
                                                  "width": 400.0, "height": 68.0, "hero_ids": list(heroes)}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake Steam cfg folder, backups in tmp, Dota closed."""
    cfg_dir = tmp_path / "steam" / "userdata" / "42" / "570" / "remote" / "cfg"
    cfg_dir.mkdir(parents=True)
    path = cfg_dir / hg.FILE_NAME
    path.write_bytes(USER_FILE.encode("utf-8"))
    monkeypatch.setattr(hg.dota_paths, "steam_path", lambda: tmp_path / "steam")
    monkeypatch.setattr(hg, "backup_dir", lambda: tmp_path / "backups")
    state = {"running": False}
    monkeypatch.setattr(hg, "dota_running", lambda: state["running"])
    return path, state, tmp_path


# ---------- the format ----------------------------------------------------------------------

def test_dumps_reproduces_the_game_format_byte_for_byte():
    data = hg.loads(USER_FILE)
    assert hg.dumps(data) == USER_FILE
    assert hg.loads("﻿" + USER_FILE) == data  # a BOM does not break reading


def test_real_user_file_round_trips_when_present():
    real = hg.grid_path(1477734386)  # read only: the real file is never written by a test
    if real is None or not real.exists():
        pytest.skip("нет файла сеток на этом ПК")
    raw = real.read_bytes()
    assert hg.dumps(hg.loads(raw.decode("utf-8"))).encode("utf-8") == raw


def test_check_shape_refuses_unknown_layouts():
    hg.check_shape(hg.loads(USER_FILE))
    for bad in ({"version": 4, "configs": []}, {"version": 3}, [], {"version": 3, "configs": [{"config_name": "x"}]},
                {"version": 3, "configs": [{"config_name": "x", "categories": [{"category_name": "y"}]}]}):
        with pytest.raises(hg.GridError):
            hg.check_shape(bad)


# ---------- merge ---------------------------------------------------------------------------

def test_merge_keeps_user_grids_and_replaces_ours_in_place():
    data = hg.loads(USER_FILE)
    old = cfg("Драфтер · Мета", (9,))
    data["configs"] = [old, data["configs"][0], cfg("Драфтер · Роли", (5,))]
    merged = hg.merge(data, [cfg("Драфтер · Мета", (1, 2)), cfg("Драфтер · Пул", (7,))])
    names = [c["config_name"] for c in merged["configs"]]
    assert names == ["Драфтер · Мета", "Моя сетка", "Драфтер · Пул"]  # replaced in place, old one dropped, new at the end
    assert merged["configs"][0]["categories"][0]["hero_ids"] == [1, 2]
    assert merged["configs"][1] is data["configs"][1]  # the user's grid is the very same object
    assert hg.merge(merged, []) ["configs"] == [data["configs"][1]]


# ---------- apply ---------------------------------------------------------------------------

def test_apply_writes_only_ours_makes_a_backup_and_keeps_the_user_part_byte_identical(env):
    path, _, tmp = env
    res = hg.apply(42, [cfg()])
    assert res["written"] == ["Драфтер · Мета"] and res["backup"] and res["others"] == 1
    assert (tmp / "backups" / res["backup"]).read_bytes() == USER_FILE.encode("utf-8")  # the copy is the original
    after = path.read_text(encoding="utf-8")
    assert after.startswith(USER_FILE[:-len("\n\t]\n}")])  # everything of the user's before our grid is untouched
    data = hg.loads(after)
    assert [c["config_name"] for c in data["configs"]] == ["Моя сетка", "Драфтер · Мета"]
    # writing the same again is idempotent: one grid of ours, one more backup
    hg.apply(42, [cfg()])
    assert path.read_text(encoding="utf-8") == after
    assert len(hg.list_backups()) == 2


def test_apply_refuses_while_dota_runs_and_changes_nothing(env):
    path, state, tmp = env
    state["running"] = True
    with pytest.raises(hg.DotaRunning):
        hg.apply(42, [cfg()])
    assert path.read_bytes() == USER_FILE.encode("utf-8") and not (tmp / "backups").exists()


def test_apply_refuses_foreign_names_and_unknown_files(env):
    path, _, _ = env
    with pytest.raises(hg.GridError, match="начинаться"):
        hg.apply(42, [cfg("Чужая сетка")])
    path.write_text('{"version": 4, "configs": []}', encoding="utf-8")
    with pytest.raises(hg.GridError, match="незнаком"):
        hg.apply(42, [cfg()])
    assert path.read_text(encoding="utf-8") == '{"version": 4, "configs": []}'
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(hg.GridError, match="повреждён"):
        hg.apply(42, [cfg()])
    assert path.read_text(encoding="utf-8") == "not json"


def test_a_failed_verification_puts_the_backup_back(env, monkeypatch):
    path, _, _ = env
    real_dumps = hg.dumps
    monkeypatch.setattr(hg, "dumps", lambda d: real_dumps(d).replace("Тир S", "Тир X"))  # the file differs from what was built
    with pytest.raises(hg.GridError, match="запись отменена"):
        hg.apply(42, [cfg()])
    assert path.read_bytes() == USER_FILE.encode("utf-8")
    assert not list(path.parent.glob("*.drafter-tmp"))


def test_apply_creates_the_file_when_there_is_none_and_removes_it_on_failure(env, monkeypatch):
    path, _, tmp = env
    path.unlink()
    assert hg.apply(42, [cfg()])["backup"] is None
    assert [c["config_name"] for c in hg.loads(path.read_text(encoding="utf-8"))["configs"]] == ["Драфтер · Мета"]
    path.unlink()
    monkeypatch.setattr(hg, "dumps", lambda d: "{broken")
    with pytest.raises(hg.GridError):
        hg.apply(42, [cfg()])
    assert not path.exists()


def test_missing_userdata_folder(env, monkeypatch):
    monkeypatch.setattr(hg.dota_paths, "steam_path", lambda: None)
    assert hg.grid_path(42) is None and hg.status(42)["found"] is False
    with pytest.raises(hg.GridError, match="не нашёл"):
        hg.apply(42, [cfg()])


# ---------- remove, restore, backups -----------------------------------------------------------

def test_remove_ours_leaves_the_users_grids(env):
    path, _, _ = env
    hg.apply(42, [cfg(), cfg("Драфтер · Роли")])
    res = hg.remove_ours(42)
    assert sorted(res["removed"]) == ["Драфтер · Мета", "Драфтер · Роли"]
    assert path.read_text(encoding="utf-8") == USER_FILE
    assert hg.remove_ours(42) == {"removed": [], "backup": None}


def test_restore_puts_a_backup_back_after_copying_the_current_file(env):
    path, state, tmp = env
    hg.apply(42, [cfg()])
    first = hg.list_backups()[0]["name"]  # = the original
    written = path.read_bytes()
    res = hg.restore(42, first)
    assert path.read_bytes() == USER_FILE.encode("utf-8")
    assert (tmp / "backups" / res["backup"]).read_bytes() == written  # the state before the restore is kept
    with pytest.raises(hg.GridError, match="нет"):
        hg.restore(42, "../evil.json")
    with pytest.raises(hg.GridError, match="нет"):
        hg.restore(42, "hero_grid_config-nothing.json")
    state["running"] = True
    with pytest.raises(hg.DotaRunning):
        hg.restore(42, first)


def test_only_the_last_twenty_backups_are_kept(env):
    path, _, tmp = env
    for i in range(24):
        b = hg.make_backup(path)
        os.utime(b, (1_700_000_000 + i, 1_700_000_000 + i))
    names = [b["name"] for b in hg.list_backups()]
    assert len(names) == hg.KEEP_BACKUPS == len(set(names))


def test_status(env):
    path, _, _ = env
    hg.apply(42, [cfg()])
    st = hg.status(42)
    assert st["found"] and st["exists"] and st["ours"] == ["Драфтер · Мета"] and st["others"] == 1 and st["error"] is None


# ---------- layout ---------------------------------------------------------------------------

def test_layout_is_inside_the_canvas_never_overlaps_and_fits_the_heroes():
    cats = [grids.Category("a", list(range(18))), grids.Category("b", list(range(40))),
            grids.Category("c", list(range(9)), 575.0), grids.Category("d", list(range(30)), 575.0),
            grids.Category("e", [1], 381.0), grids.Category("f", [], 381.0)]
    placed = grids.layout(cats)
    for c, src in zip(placed, cats):
        assert c["x_position"] >= 0 and c["x_position"] + c["width"] <= grids.CANVAS_W
        rows = -(-max(1, len(src.heroes)) // grids.per_row(c["width"]))
        assert c["height"] >= grids.HEAD_H + rows * grids.CELL_H  # no hero is cut off
    rects = [(c["x_position"], c["y_position"], c["x_position"] + c["width"], c["y_position"] + c["height"]) for c in placed]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
    assert placed[2]["y_position"] == placed[3]["y_position"] or placed[3]["x_position"] > placed[2]["x_position"]  # halves sit side by side
    assert hg.dumps({"version": 3, "configs": [{"config_name": "x", "categories": placed}]})  # the writer takes them


def _no_overlap_and_fits(placed, cats):
    for c, src in zip(placed, cats):
        assert c["x_position"] >= 0 and c["x_position"] + c["width"] <= grids.CANVAS_W
        rows = -(-max(1, len(src.heroes)) // grids.per_row(c["width"]))
        assert c["height"] >= grids.HEAD_H + rows * grids.CELL_H
    rects = [(c["x_position"], c["y_position"], c["x_position"] + c["width"], c["y_position"] + c["height"]) for c in placed]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_meta_tiers_fit_under_470():
    # tier sizes for 127 heroes by the tier list's quantiles (10/20/40/20/10%), and a few heroes more
    for n in (127, 131):
        ids = list(range(1, n + 1))
        cut = lambda q: next(i for i in range(n + 1) if i == n or (i + 0.5) / n > q)
        edges = [0, cut(0.10), cut(0.30), cut(0.70), cut(0.90), n]
        cats = grids.tier_categories({t: ids[edges[i]:edges[i + 1]] for i, t in enumerate("SABCD")})
        placed = grids.layout(cats)
        _no_overlap_and_fits(placed, cats)
        assert sorted(h for c in placed for h in c["hero_ids"]) == ids
        assert grids.bottom(placed) <= grids.MAX_BOTTOM
        assert placed[0]["y_position"] == placed[1]["y_position"] and placed[3]["y_position"] == placed[4]["y_position"]
    assert grids.bottom(grids.layout(grids.tier_categories({"S": list(range(13)), "A": list(range(25)),
            "B": list(range(51)), "C": list(range(25)), "D": list(range(13))}))) == 452


def test_pool_worst_case_fits_and_short_roles_share_a_row():
    full = [grids.Category(f"{p} · роль", list(range(grids.POOL_ROLE_TOP)), None) for p in range(5)]
    worst = full + [grids.Category("Стоит попробовать · Мид", list(range(grids.TRY_COUNT)), None)]
    placed = grids.layout(worst)
    _no_overlap_and_fits(placed, worst)
    assert grids.bottom(placed) <= grids.MAX_BOTTOM
    short = [grids.Category(f"{p}", list(range(n)), None) for p, n in enumerate([3, 7, 2])]
    placed = grids.layout(short)
    _no_overlap_and_fits(placed, short)
    assert len({c["y_position"] for c in placed}) == 1  # 4+7+4 cells: one row
    assert all(c["width"] >= grids.cells_width(grids.MIN_CELLS) for c in placed)


def test_a_grid_that_does_not_fit_is_never_written():
    with pytest.raises(hg.GridError, match="не влезает"):
        grids.config("meta", [grids.Category("Тир B", list(range(18 * 13)))])


# ---------- real data (skipped where there is none) ---------------------------------------------

needs_model = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists(), reason="нужны константы и модель")


@needs_model
def test_build_all_four_grids_on_real_data():
    from drafter.model import predictor
    try:
        pred = predictor.get()
    except FileNotFoundError:
        pytest.skip("модель не обучена")
    built = grids.build(pred, ["roles", "meta", "counters"], 61, "LEGEND_ANCIENT", 14)
    assert set(built) == {"roles", "meta", "counters"}
    roles = built["roles"]["categories"]
    assert [c["category_name"][0] for c in roles] == list("12345") and all(10 <= len(c["hero_ids"]) <= 18 for c in roles)
    tiers = built["meta"]["categories"]
    assert [c["category_name"] for c in tiers] == [f"Тир {t}" for t in "SABCD"]
    every = [h for c in tiers for h in c["hero_ids"]]
    assert len(every) == len(set(every)) > 100  # each hero in exactly one tier
    counters = built["counters"]["categories"]
    assert len(counters) == grids.COUNTER_HEROES and all(c["category_name"].startswith("Против ") and len(c["hero_ids"]) == grids.COUNTER_PER for c in counters)
    for cfg_ in built.values():
        assert cfg_["config_name"].startswith(hg.PREFIX)
        assert grids.bottom(cfg_["categories"]) <= grids.MAX_BOTTOM
    assert copy.deepcopy(built) == built


def test_unknown_grid_id():
    with pytest.raises(KeyError):
        grids.build(None, ["nope"], 61, None, 14)


# ---------- grids from the editor -------------------------------------------------------------

def editor_cfg(name="Моя арт-сетка"):
    return {"config_name": name, "extra": 1, "categories": [
        {"category_name": "<b>Керри</b>", "x_position": 10.1234567, "y_position": 20, "width": 300, "height": 90,
         "hero_ids": [1, "2"]},
        {"category_name": "#@@ @", "x_position": 5, "y_position": 400.5, "width": 30, "height": 30, "hero_ids": []},
    ]}


def test_clean_configs_prefixes_names_and_matches_the_files_shape():
    [c] = hg.clean_configs([editor_cfg()])
    assert c["config_name"] == hg.PREFIX + "Моя арт-сетка"
    assert c["extra"] == 1
    cat, art = c["categories"]
    assert cat["category_name"] == "bКерри/b"
    assert cat["x_position"] == 10.123457 and isinstance(cat["y_position"], float)
    assert cat["hero_ids"] == [1, 2]
    assert art["category_name"] == "@@ @"  # no leading #
    assert hg.clean_configs([editor_cfg(hg.PREFIX + "X")])[0]["config_name"] == hg.PREFIX + "X"
    assert hg.clean_configs([editor_cfg()], prefix=False)[0]["config_name"] == "Моя арт-сетка"


def test_clean_configs_refuses_broken_input():
    for bad in ([], [{"config_name": "a"}], [editor_cfg(), editor_cfg()],
                [{"config_name": "a", "categories": [{"category_name": "x"}]}],
                [{"config_name": "a", "categories": [{**editor_cfg()["categories"][0], "width": "wide"}]}]):
        with pytest.raises(hg.GridError):
            hg.clean_configs(bad)


def test_editor_grids_are_written_safely_and_read_back(env):
    path, _, _ = env
    ours = hg.clean_configs([editor_cfg()])
    res = hg.apply(42, ours)
    assert res["written"] == [hg.PREFIX + "Моя арт-сетка"] and res["backup"]
    data = hg.read_configs(42)
    names = [(c["config_name"], c["ours"]) for c in data["configs"]]
    assert names == [("Моя сетка", False), (hg.PREFIX + "Моя арт-сетка", True)]
    # the user's grid is byte-identical to how the game wrote it
    assert path.read_text(encoding="utf-8").startswith(USER_FILE[: USER_FILE.index("\t\t}")])


def test_export_text_is_the_games_format():
    text = hg.export_text(hg.clean_configs([editor_cfg()], prefix=False))
    assert text.startswith('{\n\t"version": 3,\n\t"configs":\n\t[')
    assert '"x_position": 10.123457' in text and not text.endswith("\n")
    assert hg.loads(text)["configs"][0]["categories"][1]["hero_ids"] == []
