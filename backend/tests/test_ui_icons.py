import httpx

from drafter.data import ui_icons as U


def test_downloads_the_first_found_and_retries_the_missing_after_a_day(monkeypatch, tmp_path):
    monkeypatch.setattr(U, "DIR", tmp_path)
    monkeypatch.setattr(U, "FAILED", tmp_path / "failed.json")
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if req.url.path.endswith("talents.svg") and "akamai" in str(req.url):
            return httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"})
        return httpx.Response(404)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert U.ensure(http, now=1000) == {"talent": "/icons/ui/talent.svg", "innate": None}
    assert (tmp_path / "talent.svg").read_bytes() == b"<svg/>"
    n = len(calls)
    U.ensure(http, now=2000)                       # innate failed an hour ago: not asked again
    assert len(calls) == n
    U.ensure(http, now=1000 + U.RETRY_AFTER + 1)   # a day later: asked again
    assert len(calls) > n and U.paths()["talent"] == "/icons/ui/talent.svg"
