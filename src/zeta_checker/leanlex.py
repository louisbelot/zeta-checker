from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

LETTERLIKE = "α-κμ-ωΑ-ΟΡ΢Τ-Ωϊ-ϻἀ-῾℀-⅏\U0001d49c-\U0001d59f"
SUBSCRIPT = "₀-₉ₐ-ₜᵢ-ᵪ"
ID_FIRST = "A-Za-z_" + LETTERLIKE
ID_REST = "A-Za-z0-9_'!?" + LETTERLIKE + SUBSCRIPT
PART = rf"(?:«[^»\n]*»|[{ID_FIRST}][{ID_REST}]*)"
IDENT = rf"{PART}(?:\.{PART})*"

_ID_REST = re.compile(rf"[{ID_REST}]")
_START = (
    rf"--|/-|«|\"|(?<![{ID_REST}])'"
    rf"|(?<![{ID_REST}.])(?:r#*\"|[smf]!\")"
)
_CODE = re.compile(_START)
_CODE_INTERP = re.compile(_START + r"|[{}]")
_BLOCK = re.compile(r"/-|-/")
_STRING = re.compile(r'(?:[^"\\]|\\.)*"', re.S)
_CHAR = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[^\n])|[^\\'\n])'")
_INTERP_TEXT = re.compile(r'\\.|[{"]', re.S)


def blank(s: str) -> str:
    return "\n".join(" " * len(line) for line in s.split("\n"))


@dataclass
class Masked:
    text: str
    flags: list[tuple[int, str]] = field(default_factory=list)


def _block_end(src: str, i: int) -> int:
    depth = 1
    for m in _BLOCK.finditer(src, i):
        depth += 1 if m.group() == "/-" else -1
        if depth == 0:
            return m.end()
    return -1


def _interp(src: str, i: int, out: list[str], flags: list) -> int:
    while True:
        m = _INTERP_TEXT.search(src, i)
        if m is None:
            out.append(blank(src[i:]))
            flags.append((i, "unterminated string"))
            return len(src)
        p = m.start()
        out.append(blank(src[i:p]))
        tok = m.group()
        if tok == '"':
            out.append('"')
            return p + 1
        if tok == "{":
            out.append("{")
            i = _code(src, p + 1, out, flags, interp=True)
            continue
        out.append(blank(tok))
        i = m.end()


def _code(src: str, i: int, out: list[str], flags: list, interp: bool = False) -> int:
    pat = _CODE_INTERP if interp else _CODE
    n = len(src)
    depth = 0
    while True:
        m = pat.search(src, i)
        if m is None:
            out.append(src[i:])
            if interp:
                flags.append((i, "unterminated interpolation"))
            return n
        p = m.start()
        tok = m.group()
        out.append(src[i:p])
        if tok == "{":
            depth += 1
            out.append(tok)
            i = p + 1
        elif tok == "}":
            out.append(tok)
            if depth == 0:
                return p + 1
            depth -= 1
            i = p + 1
        elif tok == "--":
            e = src.find("\n", p)
            e = n if e < 0 else e
            out.append(blank(src[p:e]))
            i = e
        elif tok == "/-":
            e = _block_end(src, p + 2)
            if e < 0:
                flags.append((p, "unterminated comment"))
                e = n
            out.append(blank(src[p:e]))
            i = e
        elif tok == "«":
            e = src.find("»", p + 1)
            e = n if e < 0 else e + 1
            out.append(src[p:e])
            i = e
        elif tok == "'":
            c = _CHAR.match(src, p)
            if c:
                out.append("'" + blank(src[p + 1 : c.end() - 1]) + "'")
                i = c.end()
            else:
                out.append("'")
                i = p + 1
        elif tok.endswith('!"'):
            out.append(tok)
            i = _interp(src, p + 3, out, flags)
        elif tok.startswith("r"):
            close = '"' + "#" * (len(tok) - 2)
            body = p + len(tok)
            e = src.find(close, body)
            if e < 0:
                flags.append((p, "unterminated string"))
                out.append(tok + blank(src[body:]))
                return n
            out.append(tok + blank(src[body:e]) + close)
            i = e + len(close)
        else:
            s = _STRING.match(src, p + 1)
            if s is None:
                flags.append((p, "unterminated string"))
                out.append('"' + blank(src[p + 1 :]))
                return n
            out.append('"' + blank(src[p + 1 : s.end() - 1]) + '"')
            i = s.end()


def mask(src: str) -> Masked:
    out: list[str] = []
    flags: list[tuple[int, str]] = []
    _code(src, 0, out, flags)
    return Masked("".join(out), flags)


class Lines:
    def __init__(self, src: str):
        self.src = src
        self.starts = [0] + [m.end() for m in re.finditer("\n", src)]

    def line(self, offset: int) -> int:
        return bisect_right(self.starts, offset)

    def text(self, line: int) -> str:
        a = self.starts[line - 1]
        b = self.starts[line] - 1 if line < len(self.starts) else len(self.src)
        return self.src[a:b]


def ident_before(text: str, end: int) -> int:
    i = end
    while i > 0 and (text[i - 1] == "." or _ID_REST.match(text[i - 1])):
        i -= 1
    return i


def ident_after(text: str, start: int) -> int:
    m = _TAIL.match(text, start)
    return m.end() if m else start


_TAIL = re.compile(rf"(?:\.{PART})*")
