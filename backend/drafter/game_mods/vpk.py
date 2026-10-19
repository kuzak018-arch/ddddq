"""Valve pack files (VPK v2) and compiled Panorama resources, written without Valve's tools.

Port of GridStudio's scripts/vpk.mjs (https://github.com/linsisss/dota2-grid-toolkit, GPL-3.0-only).
Only what a menu-background pack needs: one _dir.vpk with the data after the tree, and Panorama
layouts/styles in the classic compiled format (a REDI block plus the source text in DATA), the format
resourcecompiler wrote before layouts were precompiled; the game still loads it. The resource writer
is checked byte for byte against Valve's files (tests/test_game_mods.py).
  VPK: https://developer.valvesoftware.com/wiki/VPK_(file_format)
  Resources: https://github.com/ValveResourceFormat/ValveResourceFormat (Resource, ResourceEditInfo)
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import dataclass

MAGIC = 0x55AA1234
_PATH_OK = re.compile(r"^[a-z0-9_./-]+$")


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


def build_vpk(files: list[tuple[str, bytes]]) -> bytes:
    """files: [(path in the game, data)] → one VPK v2 _dir file with the data after the tree."""
    tree: dict[str, dict[str, list[tuple[str, bytes]]]] = {}  # extension → directory → entries, in order
    for raw_path, data in files:
        path = raw_path.replace("\\", "/").lower()
        if not _PATH_OK.match(path) or path.startswith("/") or ".." in path:
            raise ValueError(f"недопустимый путь в VPK: {raw_path}")
        slash = path.rfind("/")
        directory = " " if slash < 0 else path[:slash]
        base = path[slash + 1:]
        dot = base.rfind(".")
        ext = " " if dot < 0 else base[dot + 1:]
        name = base if dot < 0 else base[:dot]
        tree.setdefault(ext, {}).setdefault(directory, []).append((name, data))

    parts: list[bytes] = []
    blobs: list[bytes] = []
    offset = 0
    for ext, dirs in tree.items():
        parts.append(ext.encode() + b"\0")
        for directory, entries in dirs.items():
            parts.append(directory.encode() + b"\0")
            for name, data in entries:
                parts.append(name.encode() + b"\0")
                # crc, preload bytes, archive index 0x7fff (data follows the tree here), offset, length, terminator
                parts.append(struct.pack("<IHHIIH", crc32(data), 0, 0x7FFF, offset, len(data), 0xFFFF))
                blobs.append(data)
                offset += len(data)
            parts.append(b"\0")
        parts.append(b"\0")
    parts.append(b"\0")
    tree_bytes = b"".join(parts)
    data_bytes = b"".join(blobs)
    # header: signature, version, tree size, file data size, archive MD5 section (none),
    # other MD5 section (tree, archive section, whole file: 48 bytes), signature section (unsigned)
    header = struct.pack("<IIIIIII", MAGIC, 2, len(tree_bytes), len(data_bytes), 0, 48, 0)
    tree_md5 = _md5(tree_bytes)
    archive_md5 = _md5(b"")
    body = header + tree_bytes + data_bytes + tree_md5 + archive_md5
    return body + _md5(body)


@dataclass
class VpkFile:
    path: str
    crc: int
    offset: int
    length: int
    data: bytes


def read_vpk(blob: bytes) -> tuple[int, list[VpkFile]]:
    """The directory of a VPK v1/v2 with each file's data (single-file packs only)."""
    magic, version, tree_size = struct.unpack_from("<III", blob, 0)
    if magic != MAGIC:
        raise ValueError("это не VPK")
    start = 28 if version == 2 else 12
    at = start

    def string() -> str:
        nonlocal at
        end = blob.index(b"\0", at)
        value = blob[at:end].decode()
        at = end + 1
        return value

    files: list[VpkFile] = []
    while ext := string():
        while directory := string():
            while name := string():
                crc, preload, _archive, offset, length, _term = struct.unpack_from("<IHHIIH", blob, at)
                at += 18 + preload
                path = ("" if directory == " " else directory + "/") + name + ("" if ext == " " else "." + ext)
                begin = start + tree_size + offset
                files.append(VpkFile(path, crc, offset, length, blob[begin:begin + length]))
    return version, files


# Panorama resources: layout (.xml → .vxml_c), style (.css → .vcss_c), script, vector (.svg → .vsvg_c,
# the same text-in-DATA resource, version 2).
_PANORAMA = {
    "layout": dict(compiled="vxml", source="xml", compiler="Panorama Layout Compiler Version"),
    "style": dict(compiled="vcss", source="css", compiler="Panorama Style Compiler Version"),
    "script": dict(compiled="vjs", source="js", compiler="Panorama Script Compiler Version"),
    "vector": dict(compiled="vsvg", source="svg", compiler="Vector Graphic Version", compile="CompileVectorGraphic",
                   compiler_version=2, resource_version=2, source_first=True),
}
_KINDS = {"vxml_c": "layout", "vcss_c": "style", "vjs_c": "script", "vsvg_c": "vector"}


def _edit_info(path: str, kind: str, source_crc: int, search_path: str) -> bytes:
    """The REDI block: ten lists of records, each list followed by its own strings; string fields hold
    offsets relative to the field. `order` is the order resourcecompiler stores a record's strings in."""
    t = _PANORAMA[kind]
    stem = re.sub(r"\.[^./]+$", "", path)
    inputs = [[f"{stem}.{t['compiled']}", search_path, 0, 1], [f"{stem}.{t['source']}", search_path, source_crc, 2]]
    if t.get("source_first"):
        inputs.reverse()
    lists = [
        (inputs, [0, 1]),                                                     # input dependencies
        ([], None),
        ([["___OverrideInputData___", "BinaryBlobArg", 0, 0]], [0, 1]),       # argument dependencies
        ([[t["compiler"], t.get("compile", "CompilePanorama"), t.get("compiler_version", 1), 0]], [1, 0]),
        ([], None), ([], None), ([], None),
        ([["IsChildResource", 0]], [0]),                                     # searchable user data (int)
        ([], None), ([], None),
    ]
    head = bytearray(len(lists) * 8)
    chunks: list[bytes] = []
    size = len(head)
    written = len(head)
    for index, (records, order) in enumerate(lists):
        if not records:
            continue
        # lists start on 4 bytes; the searchable user data (list 7) on 8 (as in Valve's vsvg_c)
        size = (size + 7) & ~7 if index == 7 else (size + 3) & ~3
        start = size
        width = len(records[0]) * 4
        record_bytes = bytearray(len(records) * width)
        struct.pack_into("<II", head, index * 8, start - index * 8, len(records))
        at = start + len(record_bytes)
        strings: list[bytes] = []
        for row, record in enumerate(records):
            for column, field in enumerate(record):
                if not isinstance(field, str):
                    struct.pack_into("<I", record_bytes, row * width + column * 4, field & 0xFFFFFFFF)
            for column in order:
                encoded = record[column].encode()
                field_at = start + row * width + column * 4
                struct.pack_into("<I", record_bytes, row * width + column * 4, at - field_at)
                strings.append(encoded + b"\0")
                at += len(encoded) + 1
        chunks.append(b"\0" * (start - written))
        chunks.append(bytes(record_bytes))
        chunks.extend(strings)
        written = at
        size = at
    return bytes(head) + b"".join(chunks)


def panorama_resource(path: str, source: str | bytes, search_path: str = "dota", source_crc: int | None = None) -> bytes:
    """A compiled Panorama resource (path: its place in the game, e.g. panorama/layout/x.vxml_c)."""
    kind = _KINDS.get(path.rsplit(".", 1)[-1])
    if kind is None:
        raise ValueError(f"не Panorama-ресурс: {path}")
    body = source.encode() if isinstance(source, str) else source
    redi = _edit_info(path, kind, crc32(body) if source_crc is None else source_crc, search_path)
    data = struct.pack("<IH", crc32(body), 0) + body  # source CRC, no image table, the text
    redi_at = 16 + 2 * 12
    data_at = (redi_at + len(redi) + 15) & ~15
    out = bytearray(data_at + len(data))
    # size, header version 12, resource version, block table offset (8, right after), two blocks
    struct.pack_into("<IHHII", out, 0, len(out), 12, _PANORAMA[kind].get("resource_version", 3), 8, 2)
    for at, name, offset, length in ((16, b"REDI", redi_at, len(redi)), (28, b"DATA", data_at, len(data))):
        out[at:at + 4] = name
        struct.pack_into("<II", out, at + 4, offset - (at + 4), length)
    out[redi_at:redi_at + len(redi)] = redi
    out[data_at:] = data
    return bytes(out)


def panorama_source(blob: bytes) -> str:
    """The source text back from a classic compiled resource."""
    count = struct.unpack_from("<I", blob, 12)[0]
    for i in range(count):
        at = 16 + i * 12
        if blob[at:at + 4] != b"DATA":
            continue
        rel, size = struct.unpack_from("<II", blob, at + 4)
        offset = at + 4 + rel
        if struct.unpack_from("<H", blob, offset + 4)[0]:
            raise ValueError("ресурс с таблицей картинок не поддерживается")
        return blob[offset + 6:offset + size].decode()
    raise ValueError("в ресурсе нет блока DATA")
