from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from zeta_checker.leanlex import ID_REST, IDENT, Lines, mask

KINDS = (
    "theorem",
    "lemma",
    "def",
    "abbrev",
    "instance",
    "structure",
    "class",
    "inductive",
    "axiom",
    "opaque",
    "example",
)
_MODS = r"(?:(?:private|protected|noncomputable|partial|unsafe|nonrec|local|scoped)\s+)*"
_DECL = re.compile(
    rf"^[ \t]*(?:@\[[^\]\n]*\][ \t]*)?({_MODS})({'|'.join(KINDS)})(?![{ID_REST}])", re.M
)
_NAME = re.compile(rf"[ \t]+(?:\(priority[ \t]*:=[^)]*\)[ \t]*)?({IDENT})")
_SCOPE = re.compile(
    rf"^[ \t]*(?:noncomputable[ \t]+)?(namespace|section|end|mutual)(?![{ID_REST}])"
    rf"[ \t]*({IDENT})?",
    re.M,
)
_IMPORT = re.compile(rf"^import[ \t]+({IDENT})", re.M)
_SIG = re.compile(r"[()\[\]{}⟨⟩⦃⦄]|:=|(?<![\w])where(?![\w])|\n(?=\S)|\n[ \t]*\|")
_NEXT = re.compile(r"\n(?=\S)")
OPEN = set("([{⟨⦃")
CLOSE = set(")]}⟩⦄")
_TOKEN = re.compile(
    rf"(?<![{ID_REST}])(?:fun|forall|exists)(?![{ID_REST}])|∃!|[∀∃λ]|→|->|,|:|[()\[\]{{}}⟨⟩⦃⦄]"
)
BINDING = {"∀", "∃", "∃!", "λ", "fun", "forall", "exists"}
_WORD = re.compile(rf"{IDENT}|\d+|\S")
NOT_NAMES = {
    "fun",
    "Prop",
    "Type",
    "Sort",
    "by",
    "let",
    "have",
    "show",
    "from",
    "in",
    "if",
    "then",
    "else",
    "match",
    "with",
    "do",
    "at",
    "forall",
    "exists",
}


@dataclass
class Decl:
    kind: str
    name: str
    full: str
    file: str
    line: int
    modifiers: str
    signature: str
    body: str
    namespace: str = ""


@dataclass
class Module:
    file: str
    imports: list[str]
    decls: list[Decl] = field(default_factory=list)
    opens: list[str] = field(default_factory=list)


def squash(s: str) -> str:
    return " ".join(s.split())


def _sig_end(text: str, i: int) -> tuple[int, bool]:
    depth = 0
    for m in _SIG.finditer(text, i):
        t = m.group()
        if t in OPEN:
            depth += 1
        elif t in CLOSE:
            depth = max(depth - 1, 0)
        elif depth == 0:
            return m.start(), t == ":="
    return len(text), False


def parse(src: str, rel: str) -> Module:
    text = mask(src).text
    lines = Lines(src)
    events = [(m.start(), "decl", m) for m in _DECL.finditer(text)]
    events += [(m.start(), "scope", m) for m in _SCOPE.finditer(text)]
    events.sort(key=lambda e: e[0])
    stack: list[tuple[str, str]] = []
    mod = Module(rel, _IMPORT.findall(text))
    mod.opens = [squash(m.group(1)) for m in re.finditer(r"^[ \t]*open[ \t]+([^\n]*)", text, re.M)]
    for _, what, m in events:
        if what == "scope":
            kind, name = m.group(1), m.group(2) or ""
            if kind == "namespace":
                stack.extend(("ns", part) for part in name.split("."))
            elif kind in ("section", "mutual"):
                stack.append((kind, name))
            elif stack:
                count = max(len(name.split(".")), 1) if name else 1
                del stack[-min(count, len(stack)) :]
            continue
        mods, kind = squash(m.group(1)), m.group(2)
        n = _NAME.match(text, m.end()) if kind not in ("example",) else None
        name = n.group(1) if n else ""
        after = n.end() if n else m.end()
        end, has_body = _sig_end(text, after)
        stop = _NEXT.search(text, end)
        body_end = stop.start() if stop else len(text)
        ns = ".".join(p for k, p in stack if k == "ns")
        if name.startswith("_root_."):
            full = name[len("_root_.") :]
        else:
            full = f"{ns}.{name}" if ns and name else name
        mod.decls.append(
            Decl(
                kind=kind,
                name=name,
                full=full,
                file=rel,
                line=lines.line(m.start(2)),
                modifiers=mods,
                signature=squash(text[m.start(2) : end]),
                body=squash(text[end + 2 : body_end]) if has_body else "",
                namespace=ns,
            )
        )
    return mod


def split_signature(signature: str, name: str) -> tuple[str, str]:
    rest = (
        signature.split(name, 1)[1] if name and name in signature else signature.split(" ", 1)[-1]
    )
    depth = 0
    for m in _TOKEN.finditer(rest):
        t = m.group()
        if t in OPEN:
            depth += 1
        elif t in CLOSE:
            depth -= 1
        elif t == ":" and depth == 0:
            return rest[: m.start()].strip(), rest[m.end() :].strip()
    return rest.strip(), ""


def statement(decl: Decl) -> str:
    binders, typ = split_signature(decl.signature, decl.name)
    return f"∀ {binders}, {typ}" if binders and typ else typ


def strip_parens(s: str) -> str:
    s = s.strip()
    while s[:1] == "(" and s[-1:] == ")":
        depth = 0
        for i, ch in enumerate(s):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(s) - 1:
                return s
        s = s[1:-1].strip()
    return s


def _binder_groups(s: str) -> list[str]:
    groups, depth, start, bare = [], 0, 0, []
    for i, ch in enumerate(s):
        if ch in OPEN:
            if depth == 0:
                if s[start:i].strip():
                    bare.append(s[start:i].strip())
                start = i
            depth += 1
        elif ch in CLOSE:
            depth -= 1
            if depth == 0:
                groups.append(s[start : i + 1])
                start = i + 1
    if s[start:].strip():
        bare.append(s[start:].strip())
    return groups + bare if groups else [s.strip()]


def _binder(group: str) -> tuple[str, str]:
    inner = group[1:-1].strip() if group[:1] in "({⦃[" and group[-1:] in ")}⦄]" else group
    if group[:1] == "(" and re.match(r"_\s*:", inner):
        return "premise", inner.split(":", 1)[1].strip()
    if group[:1] == "(":
        return "binder", inner
    return "binder", group


def shape(expr: str) -> list[tuple[str, str]]:
    s = strip_parens(squash(expr))
    items: list[tuple[str, str]] = []
    while True:
        q = re.match(r"(∀|forall)(?![\w])", s)
        if q:
            depth, comma = 0, -1
            for m in _TOKEN.finditer(s, q.end()):
                t = m.group()
                if t in OPEN:
                    depth += 1
                elif t in CLOSE:
                    depth -= 1
                elif t == "," and depth == 0:
                    comma = m.start()
                    break
            if comma < 0:
                return items + [("conclusion", s)]
            items += [_binder(g) for g in _binder_groups(s[q.end() : comma])]
            s = strip_parens(s[comma + 1 :])
            continue
        parts, depth, start = [], 0, 0
        for m in _TOKEN.finditer(s):
            t = m.group()
            if t in OPEN:
                depth += 1
            elif t in CLOSE:
                depth -= 1
            elif depth == 0 and t in BINDING and m.start() > start:
                break
            elif depth == 0 and t in ("→", "->"):
                parts.append(strip_parens(s[start : m.start()]))
                start = m.end()
        last = strip_parens(s[start:])
        items += [("premise", p) for p in parts]
        if re.match(r"(∀|forall)(?![\w])", last):
            s = last
            continue
        return items + [("conclusion", last)]


def tokens(s: str) -> list[str]:
    return _WORD.findall(s)


def token_diff(ours: str, theirs: str) -> str:
    x, y = tokens(ours), tokens(theirs)
    ops = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=x, b=y, autojunk=False).get_opcodes():
        here, there = " ".join(x[i1:i2]), " ".join(y[j1:j2])
        if op == "delete":
            ops.append(f"only here: `{here}`")
        elif op == "insert":
            ops.append(f"only in reference: `{there}`")
        elif op == "replace":
            ops.append(f"`{here}` here, `{there}` in reference")
    return "; ".join(ops)


def compare(ours: str, theirs: str) -> list[tuple[str, str, str, str]]:
    a, b = shape(ours), shape(theirs)
    keys = lambda items: [(k, tuple(tokens(t))) for k, t in items]  # noqa: E731
    rows = []
    matcher = difflib.SequenceMatcher(a=keys(a), b=keys(b), autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            rows += [(k, t, t, "same") for k, t in a[i1:i2]]
            continue
        left, right = a[i1:i2], b[j1:j2]
        for n in range(max(len(left), len(right))):
            if n >= len(right):
                rows.append((left[n][0], left[n][1], "", "only here"))
            elif n >= len(left):
                rows.append((right[n][0], "", right[n][1], "only in reference"))
            else:
                (ka, ta), (kb, tb) = left[n], right[n]
                kind = ka if ka == kb else f"{ka} here, {kb} in reference"
                rows.append((kind, ta, tb, token_diff(ta, tb)))
    return rows


def names(expr: str, bound: set[str] = frozenset()) -> list[str]:
    out = []
    for w in re.findall(IDENT, expr):
        head = w.split(".", 1)[0]
        if w in NOT_NAMES or w == "_":
            continue
        if head in bound:
            if "." in w:
                out.append("." + w.split(".", 1)[1])
            continue
        out.append(w)
    return list(dict.fromkeys(out))


def bound_names(items: list[tuple[str, str]]) -> set[str]:
    out = set()
    for kind, text in items:
        if kind == "binder":
            inner = text.strip("[]{}⦃⦄ ")
            if not (text.startswith("[") and ":" not in inner):
                out.update(inner.split(":", 1)[0].split())
        out.update(re.findall(rf"(?:∃!?|∀|λ|(?<![{ID_REST}])fun)\s*\(?\s*({IDENT})", text))
    return out


_META_CMD = re.compile(
    rf"^[ \t]*(?:@\[[^\]\n]*\][ \t]*)?(?:(?:local|scoped|private)[ \t]+)*"
    rf"(?:scoped\[[^\]\n]*\][ \t]*)?"
    rf"(notation3|notation|infixl|infixr|infix|prefix|postfix|macro_rules|macro|syntax|elab_rules|elab)"
    rf"(?![{ID_REST}])",
    re.M,
)


def trace(files: Iterable[tuple[str, bytes]], wanted: set[str]) -> tuple[list, list, int]:
    wanted = {w.rsplit(".", 1)[-1] for w in wanted}
    alt = "|".join(sorted(map(re.escape, wanted), key=len, reverse=True))
    rx_decl = re.compile(rf"(?:{'|'.join(KINDS)})[ \t]+(?:[^\s:(\[{{]*\.)?(?:{alt})(?![{ID_REST}])")
    rx_atom = re.compile(rf'"[^"\n]*(?<![{ID_REST}])(?:{alt})(?![{ID_REST}])[^"\n]*"')
    rx_quote = re.compile(rf"`\(\s*(?:{alt})(?![{ID_REST}])")
    declared, overrides, count = [], [], 0
    for rel, data in files:
        count += 1
        src = data.decode("utf-8", errors="replace")
        if not (rx_decl.search(src) or rx_atom.search(src) or rx_quote.search(src)):
            continue
        text = mask(src).text
        lines = Lines(src)
        for m in _DECL.finditer(text):
            n = _NAME.match(text, m.end())
            if n and n.group(1).rsplit(".", 1)[-1] in wanted:
                declared.append((rel, lines.line(m.start(2)), m.group(2), n.group(1)))
        for m in _META_CMD.finditer(text):
            stop = _NEXT.search(text, m.end())
            seg = src[m.start() : stop.start() if stop else len(src)]
            hit = rx_atom.search(seg) or rx_quote.search(seg)
            if hit:
                overrides.append((rel, lines.line(m.start(1)), m.group(1), squash(hit.group())))
    return declared, overrides, count
