"""Two loads of one hero (or one lane pair) at once fetch each match once, and a duplicate already
in a cache file is read once."""

import threading
import time

from drafter.data import stratz_matches as sm
from drafter.lane import pairs


class FakeStratz:
    def __init__(self, **kw):
        pass

    def close(self):
        pass


def test_parallel_loads_of_one_hero_fetch_each_match_once(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "CACHE", tmp_path)
    monkeypatch.setattr(sm, "_claimed", {})
    monkeypatch.setattr(sm.stratz, "Stratz", FakeStratz)
    monkeypatch.setattr(sm, "candidates", lambda hero, exclude: [m for m in range(100, 0, -1) if m not in exclude])
    fetched = []

    def fetch(sz, mid, hero):
        fetched.append(mid)
        time.sleep(0.002)
        return {"m": mid, "pos": 1 + mid % 2, "items": [], "skills": []}

    monkeypatch.setattr(sm, "fetch_match", fetch)
    ts = [threading.Thread(target=sm.collect, args=(5, p, 40)) for p in (1, 2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(fetched) == len(set(fetched))
    lines = (tmp_path / "5.jsonl").read_text().splitlines()
    assert len(lines) == len(set(lines))


def test_duplicates_in_a_file_are_read_once(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "CACHE", tmp_path)
    monkeypatch.setattr(pairs, "CACHE", tmp_path)
    (tmp_path / "5.jsonl").write_text('{"m": 1, "pos": 1}\n{"m": 1, "pos": 1}\n{"m": 2, "unparsed": true}\n')
    assert [r["m"] for r in sm.load(5)] == [1, 2]
    (tmp_path / "1_2.jsonl").write_text('{"m": 7, "unparsed": true}\n{"m": 7, "unparsed": true}\n')
    assert len(pairs.load(2, 1)) == 1
