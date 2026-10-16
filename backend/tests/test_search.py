import pytest

from drafter import search
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "hero_index.json").exists(),
                                reason="нужны константы: drafter.cli constants")


def name(q):
    return constants.hero_by_id()[search.resolve(q)]["name"]


@pytest.mark.parametrize("query,expected", [
    ("пудж", "Pudge"),
    ("згвпу", "Pudge"),           # typed in the wrong layout
    ("ам", "Anti-Mage"),
    ("am", "Anti-Mage"),
    ("вр", "Windranger"),
    ("Шейкер", "Earthshaker"),
    ("эрс", "Earth Spirit"),
    ("invoker", "Invoker"),
])
def test_resolve(query, expected):
    assert name(query) == expected


def test_unknown():
    with pytest.raises(ValueError):
        search.resolve("абырвалг")
