"""After a data refresh every cache built from the constants is read again."""

from drafter.api import refresh
from drafter.builds import sequences, standard, tags
from drafter.data import stratz_matches


def test_clear_caches_drops_every_constants_cache(monkeypatch):
    calls = []
    for mod, name in ((stratz_matches, "_id_maps"), (sequences, "_items"), (sequences, "_abilities"),
                      (sequences, "_parents"), (tags, "_raw"), (standard, "_maps")):
        fn = getattr(mod, name)
        monkeypatch.setattr(fn, "cache_clear", lambda n=name: calls.append(n), raising=False)
    refresh.clear_caches()
    assert {"_id_maps", "_items", "_abilities", "_parents", "_raw", "_maps"} <= set(calls)
