"""Keys the user has bound in Dota (read-only), so the overlay's global hotkeys don't steal them.

Dota keeps hotkeys in Steam Cloud: userdata/<id>/570/remote/cfg/dotakeys_personal.lst
("Keys" -> action -> "Key"/"Key2"...), plus console binds in user_keys*.vcfg.
A global hotkey registered by another program swallows the combo in the game, so a combo whose
main key is bound in Dota is reported as a possible conflict (Dota adds Ctrl/Shift/Alt itself:
quick cast, queueing, pings).
"""

from __future__ import annotations

from pathlib import Path

from . import dota_paths, kv


def _files(account_id: int) -> list[Path]:
    steam = dota_paths.steam_path()
    if steam is None:
        return []
    base = steam / "userdata" / str(account_id) / "570"
    return [base / "remote" / "cfg" / "dotakeys_personal.lst", base / "remote" / "user_keys.vcfg",
            base / "local" / "cfg" / "user_keys_0_slot0.vcfg"]


def _collect(node, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and k.lower().startswith("key") and v:
                out.add(v.upper())
            else:
                _collect(v, out)


def bound_keys(account_id: int) -> set[str]:
    keys: set[str] = set()
    for f in _files(account_id):
        if not f.exists():
            continue
        data = kv.loads(f.read_text(encoding="utf-8", errors="replace"))
        _collect(data.get("KeyBindings", {}).get("Keys", {}), keys)
        bindings = data.get("config", {}).get("bindings", {})
        keys.update(k.upper() for k in bindings)
    return keys
