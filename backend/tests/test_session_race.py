"""Patches from the GSI and screen reading threads at the same time: neither is lost."""

import sys
import threading

import pytest

from drafter.api import session
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "hero_index.json").exists(), reason="нужны константы")


def test_concurrent_patches_are_all_kept():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for _ in range(200):
            session._state = session.Session()
            gate = threading.Barrier(2)

            def gsi():
                gate.wait()
                session.patch("gsi", phase="draft")

            def vision():
                gate.wait()
                session.patch("vision", enemies=[2, None, None, None, None])

            ts = [threading.Thread(target=gsi), threading.Thread(target=vision)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            s = session.get()
            assert s.phase == "draft" and s.enemies[0] == 2 and s.rev == 2
    finally:
        sys.setswitchinterval(old)
        session._state = session.Session()
