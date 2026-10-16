"""Minimal parser for Valve KeyValues text files (libraryfolders.vdf, video.txt, GSI cfg).

Only the subset Steam and Dota actually write: quoted or bare tokens, nested blocks,
`//` comments. Duplicate keys keep the last value, which is what we need for configs.
"""

from __future__ import annotations

import re

# Quoted strings are matched before comments, so "http://..." inside quotes survives.
# Escapes: \\ and \" -- but \" right before whitespace is a literal backslash closing the string,
# because Dota binds the backslash key as "\" (user_keys.vcfg, dotakeys_personal.lst).
_TOKEN = re.compile(r'"((?:[^"\\]|\\\\|\\"(?!\s)|\\(?!\\))*)"|(//[^\n]*)|([{}])|([^\s{}"]+)')


def _tokens(text: str):
    for m in _TOKEN.finditer(text):
        quoted, comment, brace, bare = m.groups()
        if comment is not None:
            continue
        if brace:
            yield brace
        elif quoted is not None:
            yield ("str", quoted.replace('\\"', '"').replace("\\\\", "\\"))
        else:
            yield ("str", bare)


def loads(text: str) -> dict:
    stack: list[dict] = [{}]
    key: str | None = None
    for tok in _tokens(text):
        if tok == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = tok[1]
        else:
            stack[-1][key] = tok[1]
            key = None
    return stack[0]


def dumps(data: dict, indent: int = 0) -> str:
    pad = "\t" * indent
    out = []
    for k, v in data.items():
        if isinstance(v, dict):
            out.append(f'{pad}"{k}"\n{pad}{{\n{dumps(v, indent + 1)}{pad}}}\n')
        else:
            out.append(f'{pad}"{k}"\t\t"{v}"\n')
    return "".join(out)
