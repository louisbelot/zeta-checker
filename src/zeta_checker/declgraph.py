from __future__ import annotations

import re
from array import array
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from zeta_checker.archive import count_lines
from zeta_checker.leanlex import ID_REST, IDENT
from zeta_checker.statements import NOT_NAMES, parse

_TOKEN = re.compile(IDENT)
_OPEN_STOP = {"in", "hiding", "renaming", "scoped", "using"}
_BINDER = re.compile(
    rf"(?<![{ID_REST}.])(?:fun|λ|∀|∃!?|∑|∏|⋃|⋂|⨆|⨅|intro|intros|rintro|obtain|have|let|set"
    rf"|generalizing|choose|ext|with)(?![{ID_REST}])"
    rf"((?:⟨[^⟩\n]*⟩|(?!(?:using|in|at)(?![{ID_REST}]))[^:=→,;⟨∈∉⊆⊂<>≤≥≠\n])*)"
)
_GROUP = re.compile(r"[({⦃\[]([^:(){}\[\]⦃⦄⟨⟩\n]*):")
_ARM = re.compile(r"\|([^|=\n]*)=>")
TACTICS = frozenset(
    "exact apply refine change show calc intro intros rintro obtain rcases cases induction"
    " simp simpa rw rwa rewrite erw nth_rewrite unfold delta dsimp norm_num ring ring_nf"
    " linarith nlinarith positivity omega decide aesop gcongr field_simp push_cast"
    " exact_mod_cast norm_cast specialize subst contradiction exfalso by_contra by_cases"
    " ext congr convert trivial assumption tauto constructor left right existsi use symm"
    " filter_upwards measurability continuity fun_prop interval_cases fin_cases choose"
    " lift clear revert generalize split_ifs refine' apply_fun conv rfl".split()
)

Pairs = Callable[[], Iterable[tuple[str, bytes]]]


@dataclass
class Graph:
    names: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    files: list[int] = field(default_factory=list)
    lines: array = field(default_factory=lambda: array("i"))
    sizes: array = field(default_factory=lambda: array("i"))
    paths: list[str] = field(default_factory=list)
    index: dict[str, int] = field(default_factory=dict)
    starts: array = field(default_factory=lambda: array("q", [0]))
    targets: array = field(default_factory=lambda: array("i"))
    repeated: int = 0

    def __len__(self) -> int:
        return len(self.names)

    def out(self, v: int) -> array:
        return self.targets[self.starts[v] : self.starts[v + 1]]

    def where(self, v: int) -> str:
        return f"{self.paths[self.files[v]]}:{self.lines[v]}"


def open_names(opens: list[str]) -> list[str]:
    out = []
    for line in opens:
        for word in line.split():
            if word in _OPEN_STOP or word.startswith("("):
                break
            out.append(word)
    return out


def local_names(text: str) -> set[str]:
    out: set[str] = set()
    for rx in (_BINDER, _GROUP, _ARM):
        for m in rx.finditer(text):
            out.update(_TOKEN.findall(m.group(1)))
    return out


def resolve(tok: str, scopes: list[str], opens: list[str], index: dict[str, int]) -> list[int]:
    if tok.startswith("_root_."):
        v = index.get(tok[len("_root_.") :])
        return [] if v is None else [v]
    while True:
        for scope in scopes:
            v = index.get(f"{scope}.{tok}" if scope else tok)
            if v is not None:
                return [v]
        hits = [index[f"{o}.{tok}"] for o in opens if f"{o}.{tok}" in index]
        if hits or "." not in tok:
            return hits
        tok = tok.rsplit(".", 1)[0]


def _scopes(ns: str) -> list[str]:
    parts = ns.split(".") if ns else []
    return [".".join(parts[:k]) for k in range(len(parts), -1, -1)]


def _label(kind: str, rel: str, line: int, name: str, ns: str) -> str:
    if name:
        return name
    return f"<{kind} {rel}:{line}>" if not ns else f"{ns}.<{kind} {rel}:{line}>"


def build(pairs: Pairs) -> Graph:
    g = Graph()
    for rel, data in pairs():
        mod = parse(data.decode("utf-8", errors="replace"), rel)
        fid = len(g.paths)
        g.paths.append(rel)
        ends = [d.line for d in mod.decls[1:]] + [count_lines(data) + 1]
        for d, end in zip(mod.decls, ends, strict=False):
            v = len(g.names)
            g.names.append(_label(d.kind, rel, d.line, d.full, d.namespace))
            g.kinds.append(d.kind)
            g.files.append(fid)
            g.lines.append(d.line)
            g.sizes.append(max(end - d.line, 1))
            if d.full:
                if d.full in g.index:
                    g.repeated += 1
                else:
                    g.index[d.full] = v
    short = {n.rsplit(".", 1)[-1] for n in g.index}
    v = 0
    for rel, data in pairs():
        mod = parse(data.decode("utf-8", errors="replace"), rel)
        opens = open_names(mod.opens)
        for d in mod.decls:
            scopes = _scopes(d.full.rpartition(".")[0] if d.full else d.namespace)
            seen: set[int] = set()
            bound = local_names(d.raw)
            for tok in set(_TOKEN.findall(d.raw)):
                if tok in NOT_NAMES or tok in TACTICS or tok.split(".", 1)[0] in bound:
                    continue
                if tok.rsplit(".", 1)[-1] not in short and "." not in tok:
                    continue
                for w in resolve(tok, scopes, opens, g.index):
                    if w != v:
                        seen.add(w)
            g.targets.extend(sorted(seen))
            g.starts.append(len(g.targets))
            v += 1
    if v != len(g.names):
        raise RuntimeError(f"second pass saw {v} declarations, first pass {len(g.names)}")
    return g


def reach(g: Graph, roots: Iterable[int]) -> list[int]:
    seen = bytearray(len(g))
    order, stack = [], list(roots)
    for r in stack:
        seen[r] = 1
    while stack:
        v = stack.pop()
        order.append(v)
        for w in g.out(v):
            if not seen[w]:
                seen[w] = 1
                stack.append(w)
    return order


def dominators(succ: Callable[[int], Iterable[int]], n: int, root: int) -> list[int]:
    order, post = [], [-1] * n
    stack = [(root, iter(succ(root)))]
    post_seen = bytearray(n)
    post_seen[root] = 1
    while stack:
        v, it = stack[-1]
        for w in it:
            if not post_seen[w]:
                post_seen[w] = 1
                stack.append((w, iter(succ(w))))
                break
        else:
            stack.pop()
            post[v] = len(order)
            order.append(v)
    preds: list[list[int]] = [[] for _ in range(n)]
    for v in order:
        for w in succ(v):
            preds[w].append(v)
    idom = [-1] * n
    idom[root] = root
    rpo = order[::-1]
    changed = True
    while changed:
        changed = False
        for v in rpo[1:]:
            new = -1
            for p in preds[v]:
                if idom[p] == -1:
                    continue
                if new == -1:
                    new = p
                    continue
                a, b = p, new
                while a != b:
                    while post[a] < post[b]:
                        a = idom[a]
                    while post[b] < post[a]:
                        b = idom[b]
                new = a
            if idom[v] != new:
                idom[v] = new
                changed = True
    return idom


@dataclass
class Tree:
    root: int
    idom: dict[int, int]
    count: Counter
    lines: Counter
    children: dict[int, list[int]]


def dominator_tree(g: Graph, roots: list[int]) -> Tree:
    nodes = reach(g, roots)
    local = {v: i + 1 for i, v in enumerate(nodes)}
    back = [-1] + nodes

    def succ(i: int):
        if i == 0:
            return [local[r] for r in roots]
        return [local[w] for w in g.out(back[i])]

    idom_local = dominators(succ, len(back), 0)
    idom = {back[i]: back[idom_local[i]] for i in range(1, len(back))}
    children: dict[int, list[int]] = {}
    for v, d in idom.items():
        children.setdefault(d, []).append(v)
    count, lines = Counter(), Counter()
    for v in reversed(_preorder(children, -1)):
        if v >= 0:
            count[v] += 1
            lines[v] += g.sizes[v]
        d = idom.get(v)
        if d is not None:
            count[d] += count[v]
            lines[d] += lines[v]
    for kids in children.values():
        kids.sort(key=lambda v: (-lines[v], g.names[v]))
    return Tree(-1, idom, count, lines, children)


def _preorder(children: dict[int, list[int]], root: int) -> list[int]:
    out, stack = [], [root]
    while stack:
        v = stack.pop()
        out.append(v)
        stack.extend(children.get(v, ()))
    return out


def spine(t: Tree, min_lines: int, depth: int) -> list[tuple[int, int]]:
    rows, stack = [], [(t.root, -1)]
    while stack:
        v, k = stack.pop()
        if k >= 0:
            rows.append((k, v))
        if k + 1 < depth:
            kids = [w for w in t.children.get(v, []) if t.lines[w] >= min_lines]
            stack.extend((w, k + 1) for w in reversed(kids))
    return rows


def folders(g: Graph, nodes: Iterable[int], depth: int = 2) -> Counter:
    out = Counter()
    for v in nodes:
        key = "/".join(g.paths[g.files[v]].split("/")[:depth])
        out[key] += g.sizes[v]
    return out


def svg(rows: list[tuple[int, str, int, str]], title: str) -> str:
    h, top, indent, bar_x, bar_w = 18, 44, 14, 640, 220
    peak = max((r[2] for r in rows), default=1) or 1
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{top + h * len(rows) + 16}"'
        ' font-family="Consolas, Menlo, monospace" font-size="12">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="12" y="22" font-size="14" fill="#111">{_esc(title)}</text>',
        f'<text x="{bar_x}" y="38" fill="#555">source lines dominated</text>',
    ]
    for i, (depth, label, value, note) in enumerate(rows):
        y = top + i * h
        x = 12 + depth * indent
        if i % 2:
            out.append(f'<rect x="0" y="{y}" width="1000" height="{h}" fill="#f2f4f7"/>')
        room = (bar_x - 16 - x) // 7
        text = label if len(label) <= room else "…" + label[-(room - 1) :]
        out.append(f'<text x="{x}" y="{y + 13}" fill="#111">{_esc(text)}</text>')
        w = max(1, round(bar_w * value / peak))
        out.append(f'<rect x="{bar_x}" y="{y + 4}" width="{w}" height="10" fill="#3b6ea5"/>')
        out.append(
            f'<text x="{bar_x + bar_w + 8}" y="{y + 13}" fill="#333">{value:,} {_esc(note)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
