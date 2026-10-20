"""Fonts for Dota 2's Panorama UI.

Port of GridStudio's scripts/dota-font.mjs (https://github.com/linsisss/dota2-grid-toolkit,
GPL-3.0-only). The game draws text with fontconfig 2.11 and FreeType 2.5 from loose files in
game/dota/panorama/fonts/ — not from VPK packs, so a font cannot go into the language folder's pack:
it has to replace those files. Radiance is almost all text (chat, tooltips, hero-grid category
names), Reaver the titles and the top menu, RadianceM the digits. A font replaces one of them when it
is saved under Valve's file name with Valve's family name inside; the install keeps Valve's files
and puts them back. Static TrueType/CFF only: that FreeType predates WOFF2 and variable instances.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

FAMILIES = {"Radiance": "text", "RadianceM": "numbers", "Reaver": "titles"}

# Valve's files and the identity inside each (name IDs 1, 2, 4, 6, 16, 17 and the weight class),
# read from the game's panorama/fonts by GridStudio. A replacement carries the same identity, so
# fontconfig picks it exactly where it picked Valve's face.
VALVE_FACES: dict[str, tuple] = {
    "radiance-black": ("Radiance Black", "Regular", "Radiance Black", "Radiance-Black", "Radiance", "Black", 900),
    "radiance-blackitalic": ("Radiance Black", "Italic", "Radiance Black Italic", "Radiance-BlackItalic", "Radiance", "Black Italic", 900),
    "radiance-bold": ("Radiance", "Bold", "Radiance Bold", "Radiance-Bold", None, None, 700),
    "radiance-bolditalic": ("Radiance", "Bold Italic", "Radiance Bold Italic", "Radiance-BoldItalic", None, None, 700),
    "radiance-light": ("Radiance", "Regular", "Radiance Light", "Radiance-Light", None, "Light", 300),
    "radiance-lightitalic": ("Radiance", "Italic", "Radiance Light Italic", "Radiance-LightItalic", None, "Light Italic", 300),
    "radiance-regular": ("Radiance", "Regular", "Radiance Regular", "Radiance-Regular", None, None, 400),
    "radiance-regularitalic": ("Radiance", "Italic", "Radiance Regular Italic", "Radiance-RegularItalic", None, "Regular Italic", 400),
    "radiance-semibold": ("Radiance Semibold", "Regular", "Radiance Semibold", "Radiance-Semibold", "Radiance", "Semibold", 600),
    "radiance-semibolditalic": ("Radiance Semibold", "Italic", "Radiance Semibold Italic", "Radiance-SemiboldItalic", "Radiance", "Semibold Italic", 600),
    "radiance-ultralight": ("Radiance UltraLight", "Regular", "Radiance UltraLight", "Radiance-UltraLight", "Radiance", "UltraLight", 200),
    "radiance-ultralightitalic": ("Radiance", "Italic", "Radiance UltraLight Italic", "Radiance-UltraLightItalic", None, "UltraLight Italic", 200),
    "radiancem-black": ("RadianceM Black", "Regular", "RadianceM Black", "RadianceM-Black", "RadianceM", "Black", 900),
    "radiancem-blackitalic": ("RadianceM Black", "Italic", "RadianceM Black Italic", "RadianceM-BlackItalic", "RadianceM", "Black Italic", 900),
    "radiancem-bold": ("RadianceM", "Bold", "RadianceM Bold", "RadianceM-Bold", None, None, 700),
    "radiancem-bolditalic": ("RadianceM", "Bold Italic", "RadianceM Bold Italic", "RadianceM-BoldItalic", None, None, 700),
    "radiancem-italic": ("RadianceM", "Italic", "RadianceM Italic", "RadianceM-Italic", "RadianceM", "Italic", 400),
    "radiancem-light": ("RadianceM", "Regular", "RadianceM Light", "RadianceM-Light", "RadianceM", "Light", 300),
    "radiancem-lightitalic": ("RadianceM", "Italic", "RadianceM Light Italic", "RadianceM-LightItalic", "RadianceM", "Light Italic", 300),
    "radiancem-regular": ("RadianceM", "Regular", "RadianceM Regular", "RadianceM-Regular", None, None, 400),
    "radiancem-regularitalic": ("RadianceM", "Italic", "RadianceM Regular Italic", "RadianceM-RegularItalic", None, "Regular Italic", 400),
    "radiancem-semibold": ("RadianceM Semibold", "Regular", "RadianceM Semibold", "RadianceM-Semibold", "RadianceM", "Semibold", 600),
    "radiancem-semibolditalic": ("RadianceM Semibold", "Italic", "RadianceM Semibold Italic", "RadianceM-SemiboldItalic", "RadianceM", "Semibold Italic", 600),
    "radiancem-ultralight": ("RadianceM UltraLight", "Regular", "RadianceM UltraLight", "RadianceM-UltraLight", "RadianceM", "UltraLight", 250),
    "reaver-black": ("Reaver Black", "Regular", "Reaver Black", "Reaver-Black", "Reaver", "Black", 900),
    "reaver-bold": ("Reaver", "Bold", "Reaver Bold", "Reaver-Bold", None, None, 700),
    "reaver-light": ("Reaver Light", "Regular", "Reaver Light", "Reaver-Light", "Reaver", "Light", 300),
    "reaver-regular": ("Reaver", "Regular", "Reaver Regular", "Reaver-Regular", None, None, 400),
    "reaver-semibold": ("Reaver SemiBold", "Regular", "Reaver SemiBold", "Reaver-SemiBold", "Reaver", "SemiBold", 600),
}
DOTA_FONT_FILES = [f"{name}.otf" for name in VALVE_FACES]
# Hero-grid art is laid out by Radiance Semibold's widths: in any other font it falls apart, so
# «Рисунки в сетке не съедут» leaves this one file Valve's.
GRID_FONT_FILE = "radiance-semibold"

CYRILLIC = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"
LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


class FontError(Exception):
    """A font the game cannot use (the message is for the user)."""


@dataclass
class Font:
    data: bytes
    signature: bytes
    tables: dict[str, bytes]
    names: dict[int, str]
    weight: int
    italic: bool
    ranges: list[tuple[int, int]] = field(default_factory=list)

    def covers(self, ch: str) -> bool:
        code = ord(ch)
        return any(a <= code <= b for a, b in self.ranges)

    def missing(self) -> dict[str, list[str]]:
        return {"latin": [c for c in LATIN if not self.covers(c)], "cyrillic": [c for c in CYRILLIC if not self.covers(c)]}


def read_font(data: bytes) -> Font:
    if len(data) < 12:
        raise FontError("файл слишком маленький для шрифта")
    signature = data[:4]
    if signature in (b"wOFF", b"wOF2"):
        raise FontError("это веб-шрифт (WOFF): нужен файл .ttf или .otf")
    if signature == b"ttcf":
        raise FontError("это коллекция шрифтов (.ttc): нужен один шрифт .ttf или .otf")
    if signature not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise FontError("это не шрифт TrueType или OpenType")
    count = struct.unpack_from(">H", data, 4)[0]
    if 12 + count * 16 > len(data):
        raise FontError("шрифт повреждён")
    tables: dict[str, bytes] = {}
    for i in range(count):
        at = 12 + i * 16
        tag = data[at:at + 4].decode("latin-1")
        offset, length = struct.unpack_from(">II", data, at + 8)
        if offset + length > len(data):
            raise FontError("шрифт повреждён")
        tables[tag] = data[offset:offset + length]
    for need in ("head", "name", "cmap", "OS/2", "hhea", "hmtx", "maxp"):
        if need not in tables:
            raise FontError(f"в шрифте нет таблицы {need}")
    if "fvar" in tables:
        raise FontError("это вариативный шрифт: Дота понимает только статичные — возьми отдельные начертания (Regular, Bold…)")
    os2 = tables["OS/2"]
    return Font(data, signature, tables, _read_names(tables["name"]), struct.unpack_from(">H", os2, 4)[0],
                bool(struct.unpack_from(">H", os2, 62)[0] & 1), _cmap_ranges(tables["cmap"]))


def _read_names(table: bytes) -> dict[int, str]:
    count, storage = struct.unpack_from(">HH", table, 2)
    names: dict[int, str] = {}
    for i in range(count):
        platform, encoding, language, nid, length, offset = struct.unpack_from(">HHHHHH", table, 6 + i * 12)
        raw = table[storage + offset:storage + offset + length]
        if platform in (0, 3):
            value = raw.decode("utf-16-be", errors="replace")
        elif platform == 1 and encoding == 0:
            value = raw.decode("latin-1")
        else:
            continue
        english = language == 0x409 if platform == 3 else language == 0 if platform == 1 else True
        if nid not in names or english:
            names[nid] = value
    return names


def _cmap_ranges(table: bytes) -> list[tuple[int, int]]:
    count = struct.unpack_from(">H", table, 2)[0]
    best = None
    for i in range(count):
        platform, encoding, offset = struct.unpack_from(">HHI", table, 4 + i * 8)
        fmt = struct.unpack_from(">H", table, offset)[0]
        if fmt == 12 and (platform == 3 and encoding == 10 or platform == 0):
            best = (12, offset)
            break
        if fmt == 4 and (platform == 3 and encoding == 1 or platform == 0) and best is None:
            best = (4, offset)
    ranges: list[tuple[int, int]] = []
    if best and best[0] == 12:
        groups = struct.unpack_from(">I", table, best[1] + 12)[0]
        for i in range(groups):
            a, b = struct.unpack_from(">II", table, best[1] + 16 + i * 12)
            ranges.append((a, b))
    elif best:
        segments = struct.unpack_from(">H", table, best[1] + 6)[0] // 2
        ends = best[1] + 14
        starts = ends + segments * 2 + 2
        for i in range(segments):
            start = struct.unpack_from(">H", table, starts + i * 2)[0]
            end = struct.unpack_from(">H", table, ends + i * 2)[0]
            if start != 0xFFFF:
                ranges.append((start, end))
    return ranges


def _name_table(original: bytes, names: dict[int, str | None]) -> bytes:
    """The name table rebuilt: the family/style names Dota looks for; other records kept (copyright,
    license, designer — the OFL requires keeping them)."""
    count, storage = struct.unpack_from(">HH", original, 2)
    records = []
    for i in range(count):
        platform, encoding, language, nid, length, offset = struct.unpack_from(">HHHHHH", original, 6 + i * 12)
        if nid in names:
            continue
        records.append((platform, encoding, language, nid, original[storage + offset:storage + offset + length]))
    for nid, value in names.items():
        if value is None:  # removed, not replaced
            continue
        records.append((3, 1, 0x409, nid, value.encode("utf-16-be")))
        records.append((1, 0, 0, nid, bytes(ord(c) & 0x7F for c in value)))
    records.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    head = 6 + len(records) * 12
    out = bytearray(struct.pack(">HHH", 0, len(records), head))
    blob = bytearray()
    for platform, encoding, language, nid, data in records:
        out += struct.pack(">HHHHHH", platform, encoding, language, nid, len(data), len(blob))
        blob += data
    return bytes(out + blob)


def _checksum(data: bytes) -> int:
    padded = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF


def _write_font(signature: bytes, tables: dict[str, bytes]) -> bytes:
    tags = sorted(tables)
    count = len(tags)
    selector = count.bit_length() - 1
    search = (2 ** selector) * 16
    size = 12 + count * 16
    offsets = []
    for tag in tags:
        offsets.append(size)
        size += (len(tables[tag]) + 3) & ~3
    out = bytearray(size)
    struct.pack_into(">IHHHH", out, 0, 0x4F54544F if signature == b"OTTO" else 0x00010000, count, search, selector, count * 16 - search)
    for i, tag in enumerate(tags):
        table = tables[tag]
        struct.pack_into(">4sIII", out, 12 + i * 16, tag.encode("latin-1"), _checksum(table), offsets[i], len(table))
        out[offsets[i]:offsets[i] + len(table)] = table
    head_at = offsets[tags.index("head")]
    struct.pack_into(">I", out, head_at + 8, (0xB1B0AFBA - _checksum(bytes(out))) & 0xFFFFFFFF)
    return bytes(out)


def dota_face(font: Font, file: str) -> bytes:
    """One of Valve's font files (name without .otf) made from `font`."""
    family, style, full, postscript, typographic, typographic_style, weight = VALVE_FACES[file]
    italic, bold, regular = "Italic" in style, "Bold" in style, style == "Regular"
    tables = dict(font.tables)
    # IDs 16/17 only where Valve's file has them; stale ones from the source font go
    tables["name"] = _name_table(font.tables["name"], {1: family, 2: style, 4: full, 6: postscript, 16: typographic, 17: typographic_style})
    os2 = bytearray(font.tables["OS/2"])
    struct.pack_into(">H", os2, 4, weight)
    struct.pack_into(">H", os2, 8, 0)  # installable: nothing restricts use
    selection = struct.unpack_from(">H", os2, 62)[0]
    selection = (selection & ~0b1100001) | (1 if italic else 0) | (0b100000 if bold else 0) | (0b1000000 if regular else 0)
    struct.pack_into(">H", os2, 62, selection)
    tables["OS/2"] = bytes(os2)
    head = bytearray(font.tables["head"])
    struct.pack_into(">I", head, 8, 0)
    struct.pack_into(">H", head, 44, (1 if bold else 0) | (2 if italic else 0))  # macStyle
    tables["head"] = bytes(head)
    return _write_font(font.signature, tables)


def font_pack(fonts: list[Font], families: list[str], keep: list[str] = ()) -> dict[str, bytes]:
    """{Valve's file name: data}: each of Valve's files in the chosen families gets the face closest in
    weight (an italic where there is one). `keep`: Valve's files (without .otf) left as they are."""
    if not fonts:
        raise FontError("нет шрифта")
    out: dict[str, bytes] = {}
    for file, face in VALVE_FACES.items():
        family = face[4] or face[0]
        if family not in families or file in keep:
            continue
        weight, italic = face[6], "Italic" in face[1]
        pick = sorted(fonts, key=lambda f: ((f.italic != italic), abs(f.weight - weight), -f.weight))[0]
        out[f"{file}.otf"] = dota_face(pick, file)
    return out


def catalog_dir() -> Path:
    return config.SHARED / "dota-fonts"


def catalog() -> list[dict]:
    """Free fonts with Cyrillic (SIL OFL 1.1) shipped with the app, from GridStudio's catalog."""
    data = json.loads((catalog_dir() / "fonts.json").read_text(encoding="utf-8"))
    return data["fonts"]


def catalog_fonts(font_id: str) -> list[Font]:
    entry = next((f for f in catalog() if f["id"] == font_id), None)
    if entry is None:
        raise FontError("нет такого шрифта в подборке")
    return [read_font((catalog_dir() / font_id / f["file"]).read_bytes()) for f in entry["files"]]
