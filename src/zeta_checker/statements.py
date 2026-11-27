from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Iterable
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
    raw: str = field(default="", repr=False)


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
                raw=text[m.start(2) : body_end],
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


_INNER = BINDING | {"∑", "∏", "⋃", "⋂", "⨆", "⨅", "Σ", "Π"}
_PRED = {">", "<", "≥", "≤", "∈", "∉", "≠", "⊆", "⊂", "|", "//"}
_BODY = {",", "=>", "↦"}
_LEX = re.compile(rf"(?<![{ID_REST}])(?:fun|forall|exists)(?![{ID_REST}])|{IDENT}|∃!|=>|//|\d+|\S")
_SETOF = re.compile(rf"\{{\s*({IDENT})\s*(?::[^|{{}}]*)?(?:\||//)")


def rename(
    text: str, top: dict[str, str], fresh: Callable[[int, str], str]
) -> tuple[str, list[str]]:
    out, last, depth = [], 0, 0
    scopes: list[tuple[int, dict[str, str]]] = []
    inner: list[str] = []
    binding = None

    def bind(name: str) -> str:
        new = fresh(len(inner), name)
        inner.append(name)
        scopes[-1][1][name] = new
        return new

    def lookup(name: str) -> str | None:
        for _, m in reversed(scopes):
            if name in m:
                return m[name]
        return top.get(name)

    for m in _LEX.finditer(text):
        t, new = m.group(), None
        if t in CLOSE:
            depth -= 1
            while scopes and depth < scopes[-1][0]:
                scopes.pop()
            if binding is not None and depth < binding[0]:
                binding = None
            elif binding is not None and depth == binding[0]:
                binding[2] = False
        elif binding is not None:
            d0, bare, group = binding
            if t in OPEN:
                depth += 1
                if depth == d0 + 1:
                    binding[2] = bare or t == "["
            elif depth == d0 and t in _BODY:
                binding = None
            elif t == ":" or t in _PRED:
                binding[1 if depth == d0 else 2] = True
            elif not (bare if depth == d0 else group) and re.fullmatch(IDENT, t):
                if t not in NOT_NAMES:
                    new = bind(t)
        elif t in _INNER:
            scopes.append((depth, {}))
            binding = [depth, False, False]
        elif t in OPEN:
            if t == "{" and (s := _SETOF.match(text, m.start())):
                depth += 1
                scopes.append((depth, {}))
                out.append(text[last : s.start(1)] + bind(s.group(1)))
                last = s.end(1)
                continue
            depth += 1
        if new is None and m.start() >= last and re.fullmatch(IDENT, t):
            head, dot, rest = t.partition(".")
            if (to := lookup(head)) is not None:
                new = to + dot + rest
        if new is not None and m.start() >= last:
            out.append(text[last : m.start()] + new)
            last = m.end()
    out.append(text[last:])
    return "".join(out), inner


_BINDER_PRED = re.compile(rf"({IDENT})\s*(>|<|≥|≤|∈|∉|≠|⊆|⊂)\s*(.+)$")


def _split(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out = []
    for k, t in items:
        vs, sep, typ = t.partition(":")
        vs = vs.split()
        if k == "binder" and (m := _BINDER_PRED.fullmatch(t)) and m.group(1) not in NOT_NAMES:
            out += [(k, m.group(1)), ("premise", t)]
        elif k == "binder" and t[:1] != "[" and len(vs) > 1 and all(map(_is_ident, vs)):
            out += [(k, f"{v} : {typ.strip()}" if sep else v) for v in vs]
        else:
            out.append((k, t))
    return out


def _is_ident(v: str) -> bool:
    return re.fullmatch(IDENT, v) is not None


def _binder_name(item: tuple[str, str]) -> str | None:
    k, t = item
    if k != "binder" or t[:1] == "[":
        return None
    v = t.split(":", 1)[0].strip()
    return v if re.fullmatch(IDENT, v) else None


def _nondep(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out = []
    for i, it in enumerate(items):
        v = _binder_name(it)
        later = " ".join(t for _, t in items[i + 1 :])
        used = v is not None and any(w.split(".", 1)[0] == v for w in re.findall(IDENT, later))
        if v is not None and ":" in it[1] and not used:
            out.append(("premise", it[1].split(":", 1)[1].strip()))
        else:
            out.append(it)
    return out


def _canonical(a, b):
    def text(item, m, fresh=lambda i, _: f"§{i}"):
        v = _binder_name(item)
        if v is None:
            return rename(item[1], m, fresh)[0]
        typ = item[1].partition(":")[2].strip()
        return m.get(v, v) + (" : " + rename(typ, m, fresh)[0] if typ else "")

    ma: dict[str, str] = {}
    mb: dict[str, str] = {}
    vb = [(j, _binder_name(it)) for j, it in enumerate(b) if _binder_name(it)]
    start = 0
    for it in a:
        v = _binder_name(it)
        if v is None:
            continue
        mine = text(("premise", it[1].partition(":")[2]), ma)
        for n, (j, w) in enumerate(vb[start:], start):
            if text(("premise", b[j][1].partition(":")[2]), mb) == mine:
                ma[v] = mb[w] = f"§v{len(ma)}"
                start = n + 1
                break
    for v in filter(None, map(_binder_name, a)):
        ma.setdefault(v, f"§a.{v}")
    for _, w in vb:
        mb.setdefault(w, f"§b.{w}")
    back = {c: w for w, c in mb.items()}
    to_theirs = {v: back.get(c, v) for v, c in ma.items()}
    return [text(it, ma) for it in a], [text(it, mb) for it in b], to_theirs


def _display(ours: str, theirs: str, to_theirs: dict[str, str]) -> str:
    _, names_b = rename(theirs, {}, lambda i, n: n)
    out, _ = rename(ours, to_theirs, lambda i, n: names_b[i] if i < len(names_b) else n)
    return out


def _brackets(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        (k, t[1:-1].strip()) if k == "binder" and t[:1] in "{⦃" and t[-1:] in "}⦄" else (k, t)
        for k, t in items
    ]


def _heads(items: list[tuple[str, str]]) -> dict[str, str]:
    out = {}
    for k, t in items:
        if k == "binder" and ":" in t:
            names, typ = t.strip("()[]{}⦃⦄ ").split(":", 1)
            words = typ.split()
            for v in names.split():
                out[v] = words[0] if words else ""
    return out


def _undot(items: list[tuple[str, str]], heads: dict[str, str], other: str):
    def sub(m: re.Match) -> str:
        v, _, f = m.group().partition(".")
        full = f"{heads.get(v)}.{f} {v}"
        return full if f and heads.get(v) and full in other else m.group()

    return [(k, re.sub(IDENT, sub, t)) for k, t in items]


_SAME = {"λ": "fun", "forall": "∀", "exists": "∃"}


def _key(text: str) -> tuple[str, ...]:
    return tuple(_SAME.get(t, t) for t in tokens(text.replace("->", "→").replace("↦", "=>")))


def compare(ours: str, theirs: str) -> list[tuple[str, str, str, str]]:
    a, b = _split(_brackets(shape(ours))), _split(_brackets(shape(theirs)))
    heads = _heads(a) | _heads(b)
    a, b = (
        _nondep(_undot(a, heads, " ".join(t for _, t in b))),
        _nondep(_undot(b, heads, " ".join(t for _, t in a))),
    )
    ca, cb, to_theirs = _canonical(a, b)
    ka = [(k, _key(c)) for (k, _), c in zip(a, ca, strict=True)]
    kb = [(k, _key(c)) for (k, _), c in zip(b, cb, strict=True)]
    rows: list = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ka, b=kb, autojunk=False).get_opcodes():
        if op == "equal":
            rows += [
                (a[i][0], a[i][1], b[j][1], "same", ka[i])
                for i, j in zip(range(i1, i2), range(j1, j2), strict=True)
            ]
            continue
        for n in range(max(i2 - i1, j2 - j1)):
            i, j = i1 + n, j1 + n
            if j >= j2:
                rows.append((a[i][0], a[i][1], "", "only here", ka[i]))
            elif i >= i2:
                rows.append((b[j][0], "", b[j][1], "only in reference", kb[j]))
            else:
                (x, ta), (y, tb) = a[i], b[j]
                kind = x if x == y else f"{x} here, {y} in reference"
                diff = token_diff(_display(ta, tb, to_theirs), tb)
                rows.append((kind, ta, tb, diff or ("binding differs" if x == y else ""), ka[i]))
    here: dict = {}
    for n, r in enumerate(rows):
        if r[3] == "only here":
            here.setdefault(r[4][1], []).append(n)
    for n, r in enumerate(rows):
        if r is None or r[3] != "only in reference":
            continue
        if spot := here.get(r[4][1]):
            j = spot.pop(0)
            rows[j] = (rows[j][0], rows[j][1], r[2], "moved", None)
            rows[n] = None
    return [r[:4] for r in rows if r is not None]


def alpha_equal(ours: str, theirs: str) -> bool:
    return all(r[3] == "same" for r in compare(ours, theirs))


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


_CONTEXT = re.compile(
    rf"^[ \t]*(?:@\[[^\]\n]*\][ \t]*)?(?:(?:local|scoped|private)[ \t]+)*"
    rf"(instance|attribute|set_option|notation3|notation|infixl|infixr|infix|prefix|postfix"
    rf"|macro_rules|macro|syntax|elab_rules|elab|open|export|variable|unif_hint|deriving)"
    rf"(?![{ID_REST}])",
    re.M,
)


def context(src: str) -> list[tuple[int, str, str]]:
    text = mask(src).text
    lines = Lines(src)
    out = []
    for m in _CONTEXT.finditer(text):
        end = text.find("\n", m.start())
        line = text[m.start() : end if end >= 0 else len(text)]
        out.append((lines.line(m.start(1)), m.group(1), squash(line)))
    return out
