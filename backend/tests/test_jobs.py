import time

from fastapi.testclient import TestClient

from drafter.api import app as api
from drafter.api import events


def _wait(job, timeout=5):
    t0 = time.time()
    while job.status == "running" and time.time() - t0 < timeout:
        time.sleep(0.02)


def test_job_success_and_events(monkeypatch):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    with TestClient(api.app) as c, c.websocket_connect("/events") as ws:
        assert ws.receive_json()["type"] == "hello"

        def work(log):
            log("шаг 1")
            log("шаг 2")

        job = events.jobs.start("test-ok", work)
        _wait(job)
        assert job.status == "done" and job.log == ["шаг 1", "шаг 2"]
        got = [ws.receive_json() for _ in range(3)]
        assert [e.get("line") for e in got[:2]] == ["шаг 1", "шаг 2"]
        assert got[2]["status"] == "done"
        assert c.get(f"/jobs/{job.id}").json()["status"] == "done"


def test_job_failure_is_reported():
    def boom(log):
        raise ValueError("сломалось")

    job = events.jobs.start("test-fail", boom)
    _wait(job)
    assert job.status == "failed" and "сломалось" in job.error


def test_same_kind_job_not_started_twice():
    import threading
    gate = threading.Event()
    j1 = events.jobs.start("test-once", lambda log: gate.wait(2))
    j2 = events.jobs.start("test-once", lambda log: None)
    assert j1.id == j2.id
    gate.set()
    _wait(j1)
