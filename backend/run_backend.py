"""Entry point of the bundled backend (drafter-backend.exe, built without a console)."""

import multiprocessing
import sys


def _ensure_streams():
    # A windowed exe started without redirected handles has no stdout/stderr; uvicorn's logging
    # would crash on the first message, so write to a log file in the user's data folder instead.
    if sys.stdout is None or sys.stderr is None:
        from drafter import config
        log_dir = config.ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        f = open(log_dir / "backend.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _ensure_streams()
    from drafter.api.__main__ import main
    main()
