"""The backend's output survives a non-UTF-8 console (cp1251 on Russian Windows)."""

import io
import sys

from drafter.api.__main__ import utf8_streams


def test_utf8_streams_on_a_cp1251_log(monkeypatch):
    raw_out, raw_err = io.BytesIO(), io.BytesIO()
    out = io.TextIOWrapper(raw_out, encoding="cp1251")
    err = io.TextIOWrapper(raw_err, encoding="cp1251")
    try:
        print("✓", file=out)
        out.flush()
    except UnicodeEncodeError:
        pass
    else:
        raise AssertionError("cp1251 should not take ✓: the test would prove nothing")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    utf8_streams()
    print("  ✓ героев: 127 ⚠ матчей нового патча пока 0")
    print("ошибка ✗", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    assert "✓ героев: 127 ⚠".encode() in raw_out.getvalue()
    assert "ошибка ✗".encode() in raw_err.getvalue()


def test_utf8_streams_without_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)   # a windowed exe started without handles
    monkeypatch.setattr(sys, "stderr", None)
    utf8_streams()
