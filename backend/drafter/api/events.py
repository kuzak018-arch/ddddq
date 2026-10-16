"""Events pushed to the UI over WebSocket (job progress now; GSI and screen reading later)
and background jobs such as "refresh data after a patch"."""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable


class Bus:
    """Fan-out of JSON events to every connected WebSocket; safe to publish from worker threads."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queues: set[asyncio.Queue] = set()

    def bind(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self.queues.discard(q)

    def _put(self, event: dict):
        for q in list(self.queues):
            if q.full():
                q.get_nowait()  # drop the oldest for a slow client
            q.put_nowait(event)

    def publish(self, type_: str, **data):
        event = {"type": type_, "ts": time.time(), **data}
        if self.loop is None or self.loop.is_closed():
            return  # no server loop (CLI, tests, shutdown): nobody to deliver to
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self._put(event)
        else:
            self.loop.call_soon_threadsafe(self._put, event)


bus = Bus()


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"          # running | done | failed
    started: float = field(default_factory=time.time)
    finished: float | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None

    def public(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status, "started": self.started,
                "finished": self.finished, "log": self.log[-200:], "error": self.error}


class Jobs:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def running(self, kind: str) -> Job | None:
        return next((j for j in self.jobs.values() if j.kind == kind and j.status == "running"), None)

    def start(self, kind: str, fn: Callable[[Callable[[str], None]], None]) -> Job:
        with self._lock:
            if j := self.running(kind):
                return j
            job = Job(id=uuid.uuid4().hex[:12], kind=kind)
            self.jobs[job.id] = job

        def log(line: str):
            job.log.append(line)
            bus.publish("job", id=job.id, kind=kind, status=job.status, line=line)

        def run():
            try:
                fn(log)
                job.status = "done"
            except Exception as e:  # report any failure to the UI instead of dying silently
                job.status, job.error = "failed", f"{type(e).__name__}: {e}"
                job.log.append(traceback.format_exc())
            job.finished = time.time()
            bus.publish("job", id=job.id, kind=kind, status=job.status, error=job.error)

        threading.Thread(target=run, name=f"job-{kind}", daemon=True).start()
        return job


jobs = Jobs()
