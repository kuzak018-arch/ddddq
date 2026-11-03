"""Screen reading after an update: the old learning goes once; placeholders are not learned; a
template that «finds» one hero everywhere is put aside."""

import json

import numpy as np

from drafter.vision import auto, calibration, collector, layout, matcher, migrate, reader


def _paths(monkeypatch, tmp_path):
    v = tmp_path / "vision"
    monkeypatch.setattr(migrate, "DIR", v)
    monkeypatch.setattr(migrate, "MARK", v / "format.json")
    monkeypatch.setattr(matcher, "LEARNED", v / "learned")
    monkeypatch.setattr(matcher, "QUARANTINE", v / "learned-quarantine")
    monkeypatch.setattr(calibration, "PATH", v / "calibration.json")
    monkeypatch.setattr(collector, "DRAFTS", v / "collected")
    monkeypatch.setattr(collector, "SNAPSHOTS", v / "snapshots")
    monkeypatch.setattr(layout, "PATH", v / "layout.json")
    monkeypatch.setattr(auto, "STATE", v / "auto.json")
    return v


def test_old_learning_is_cleaned_once(monkeypatch, tmp_path):
    v = _paths(monkeypatch, tmp_path)
    (v / "learned" / "91").mkdir(parents=True)
    (v / "learned" / "91" / "a.png").write_bytes(b"png")
    (v / "calibration.json").write_text("{}")
    (v / "collected" / "d1").mkdir(parents=True)
    (v / "collected" / "d1" / "f.jpg").write_bytes(b"jpg")
    (v / "snapshots").mkdir()
    (v / "snapshots" / "auto-1.jpg").write_bytes(b"x")
    (v / "snapshots" / "wizard.png").write_bytes(b"x")
    (v / "layout.json").write_text("{}")
    (v / "auto.json").write_text(json.dumps({"manual_off": True, "proven": True}))
    out = migrate.run()
    assert out == {"learned": 1, "collected": 1, "calibration": True}
    assert not (v / "learned").exists() and (v / "learned-old" / "91" / "a.png").exists()   # a backup
    assert (v / "calibration-old.json").exists() and not (v / "calibration.json").exists()
    assert not (v / "collected").exists() and not (v / "layout.json").exists()
    assert not (v / "snapshots" / "auto-1.jpg").exists() and (v / "snapshots" / "wizard.png").exists()
    assert json.loads((v / "auto.json").read_text()) == {"manual_off": True}   # proven again from scratch
    # only once: what is learned after it stays
    (v / "learned" / "5").mkdir(parents=True)
    (v / "learned" / "5" / "b.png").write_bytes(b"png")
    assert migrate.run() is None and (v / "learned" / "5" / "b.png").exists()


def test_new_install_only_marks(monkeypatch, tmp_path):
    v = _paths(monkeypatch, tmp_path)
    assert migrate.run() == {"learned": 0, "collected": 0, "calibration": False}
    assert migrate.version() == migrate.FORMAT


def _texture(seed):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(90, 40, (40, 59, 3)), 0, 255).astype(np.uint8)


def test_a_placeholder_like_another_slot_is_not_learned(monkeypatch, tmp_path):
    _paths(monkeypatch, tmp_path)
    monkeypatch.setattr(matcher, "contradicts_art", lambda h, c: False)
    empty = _texture(1)
    twin = np.clip(empty.astype(int) + 3, 0, 255).astype(np.uint8)       # the next empty slot: the same picture
    assert matcher.looks_like_another_slot(empty, [empty, twin, _texture(2)])
    assert matcher.learn(91, empty, others=[empty, twin]) is None
    assert not matcher.looks_like_another_slot(empty, [empty, _texture(2), _texture(3)])
    assert matcher.learn(91, empty, others=[empty, _texture(2)]) is not None


def test_one_hero_in_many_slots_is_dropped_and_quarantined(monkeypatch, tmp_path):
    v = _paths(monkeypatch, tmp_path)
    (v / "learned" / "91").mkdir(parents=True)
    (v / "learned" / "91" / "a.png").write_bytes(b"png")
    S = matcher.SlotResult
    res = {"warnings": [], "radiant": [S(91, 0.9, 0.1, []), S(91, 0.9, 0.1, []), S(5, 0.9, 0.1, []), S(None, 0, 0, []), S(None, 0, 0, [])],
           "dire": [S(91, 0.9, 0.1, []), S(7, 0.9, 0.1, []), S(None, 0, 0, []), S(None, 0, 0, []), S(None, 0, 0, [])], "bans": []}
    first = res["radiant"][0]
    reader._drop_repeated(res)
    assert [r.hero for r in res["radiant"]][:3] == [None, None, 5] and res["dire"][0].hero is None and res["dire"][1].hero == 7
    assert first.hero == 91          # the bank's cached result is not changed
    assert (v / "learned-quarantine" / "91" / "a.png").exists() and not list((v / "learned" / "91").glob("*.png"))
    assert "карантин" in res["warnings"][0]
    two = {"warnings": [], "radiant": [S(3, 0.9, 0.1, []), S(3, 0.9, 0.1, [])], "dire": [], "bans": []}
    reader._drop_repeated(two)       # two slots: the runner's one-hero-one-slot rule decides
    assert [r.hero for r in two["radiant"]] == [3, 3] and not two["warnings"]
