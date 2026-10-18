"""Run the API: python -m drafter.api [--port 47900] [--token ...]
The Tauri shell starts this as a sidecar with a random token; for development no token is needed."""

import argparse
import os
import sys
import threading

import uvicorn


def watch_parent() -> None:
    """Quit as soon as the shell that started us is gone (DRAFTER_PARENT_PID). The shell also puts
    us into a Job Object that dies with it; this covers the case where that failed."""
    pid = os.environ.get("DRAFTER_PARENT_PID", "")
    if sys.platform != "win32" or not pid.isdigit():
        return
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    SYNCHRONIZE, INFINITE, ERROR_INVALID_PARAMETER = 0x00100000, 0xFFFFFFFF, 87
    handle = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        if ctypes.get_last_error() == ERROR_INVALID_PARAMETER:   # no such process: already gone
            os._exit(0)
        return
    def wait():
        k32.WaitForSingleObject(handle, INFINITE)
        os._exit(0)   # caches are appended or replaced atomically, nothing to flush
    threading.Thread(target=wait, name="parent-watch", daemon=True).start()


def utf8_streams() -> None:
    """stdout and stderr in UTF-8 whatever Windows' code page is. The shell sets PYTHONIOENCODING, but
    the bundled exe may run an isolated interpreter that ignores PYTHON* variables; then the log the
    shell redirects to a file is cp1251, and a "✓" or "⚠" printed by a refresh step raises
    UnicodeEncodeError and fails the whole job. Reconfiguring here does not depend on the env."""
    for s in (sys.stdout, sys.stderr):
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # a stream that cannot be reconfigured: leave it as it is
                pass


def main():
    utf8_streams()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=47900)
    ap.add_argument("--token", default=os.environ.get("DRAFTER_TOKEN"))
    args = ap.parse_args()
    watch_parent()
    if args.token:
        os.environ["DRAFTER_TOKEN"] = args.token
    # first start of the installed app: seed data must be on disk before modules read it
    from drafter import config
    config.ensure_seed()
    # import the app object directly (not by string): in the bundled exe a failing import then
    # shows its real traceback instead of uvicorn's generic "could not import module"
    from drafter.api.app import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
