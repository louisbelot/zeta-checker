from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from zeta_checker.pdftext import MARK

KINDS = (
    "Theorem",
    "Proposition",
    "Lemma",
    "Corollary",
    "Definition",
    "Conjecture",
    "Hypothesis",
    "Assumption",
    "Claim",
    "Remark",
    "Example",
    "Notation",
    "Construction",
)
NUM = r"[A-Z]?\d+(?:\.\d+)*"
_KIND = "|".join(KINDS)
_TITLE = r"(?:[^()\n]|\((?:[^()\n]|\([^()\n]*\))*\))*"
_HEAD = re.compile(
    rf"^[ \t]*({_KIND})[ \t]+({NUM})(?!\.?\d)[ \t]*"
    rf"(?:[ \t]\(({_TITLE})(?:\)\.|$)|\.)(?=\s|$)",
    re.M,
)
_MENTION = re.compile(rf"(?<![A-Za-z])({_KIND})s?\s+({NUM})(?!\.?\d)")
_BRACKET = re.compile(r"\[[^\[\]\n]{1,300}\]")
_EQUATION = re.compile(rf"\(({NUM})\)")
_BIB = re.compile(r"^\[([^\]\n]{1,40})\][ \t]+(.*)$")
_OUTLINE = re.compile(r"^( *)(.*?)  \.\.  ?(\d*)$")

MARKERS = {
    "editorial": r"\bTODO\b|\bFIXME\b|\bXXX\b|\?\?|\bto be (?:written|completed|added|filled in)\b"
    r"|\bplaceholder\b|\bcitation needed\b",
    "note": r"^\s*\d+ ?(?:insert|correct|state and prove|check|double-check|fix|add|complete)\b"
    r"|^\s*\d+ ?\w+ should (?:double-)?check\b",
    "deferred": r"\bto appear\b|\bin preparation\b|\bforthcoming\b|\bfuture work\b"
    r"|\b(?:in|a) (?:later|future|forthcoming|separate) (?:version|paper|work|article)\b"
    r"|\bwill be (?:treated|addressed|proved|written|given) (?:elsewhere|later)\b",
    "omitted": r"\bleft to the reader\b|\bwe omit\b|\bomitted\b|\bproof sketch\b"
    r"|\bsketch of (?:the )?proof\b|\bwe do not (?:prove|give|include)\b|\bdetails are left\b",
}


@dataclass
class Result:
    kind: str
    num: str
    title: str
    page: int
    line: int
    offset: int

    @property
    def label(self) -> str:
        return f"{self.kind} {self.num}"


@dataclass
class Text:
    body: str
    starts: list[int]
    pages: list[int]

    def where(self, offset: int) -> tuple[int, int]:
        i = bisect_right(self.starts, offset) - 1
        line = self.body.count("\n", self.starts[i], offset) if i >= 0 else 0
        return (self.pages[i] if i >= 0 else 0), line


@dataclass
class Triage:
    results: list[Result]
    edges: Counter
    dangling: Counter
    duplicates: dict[str, list[Result]]
    gaps: dict[str, list[tuple[str, str]]]
    markers: list[tuple[str, int, int, str]]
    citations: dict[str, list[int]]
    bibliography: dict[str, str]
    chapters: list[tuple[str, int, int]] = field(default_factory=list)

    def indegree(self) -> Counter:
        out = Counter()
        for (_, dst), _n in self.edges.items():
            out[dst] += 1
        return out

    def as_dict(self) -> dict:
        return {
            "chapters": self.chapters,
            "results": [asdict(r) for r in self.results],
            "edges": [[a, b, n] for (a, b), n in sorted(self.edges.items())],
            "dangling": dict(self.dangling),
            "duplicates": {k: [asdict(r) for r in v] for k, v in self.duplicates.items()},
            "gaps": self.gaps,
            "markers": self.markers,
            "citations": self.citations,
            "bibliography": self.bibliography,
        }


def load(text: str) -> Text:
    starts, pages = [], []
    for m in MARK.finditer(text):
        starts.append(m.end() + 1)
        pages.append(int(m.group(1)))
    return Text(text, starts, pages)


def results(doc: Text) -> list[Result]:
    out = []
    for m in _HEAD.finditer(doc.body):
        eol = doc.body.find("\n", m.end())
        rest = doc.body[m.end() : eol if eol >= 0 else len(doc.body)]
        if doc.body[m.start()] not in " \t" and m.group(3) is None and not rest.strip():
            continue
        page, line = doc.where(m.start())
        title = " ".join((m.group(3) or "").split())
        out.append(Result(m.group(1), m.group(2), title, page, line + 1, m.start()))
    return out


def _blank_brackets(s: str) -> str:
    return _BRACKET.sub(lambda m: " " * len(m.group()), s)


def cross_refs(doc: Text, found: list[Result]) -> tuple[Counter, Counter]:
    known = {r.num for r in found}
    heads = {r.offset for r in found}
    offsets = [r.offset for r in found]
    edges, dangling = Counter(), Counter()
    body = _blank_brackets(doc.body)
    for m in _MENTION.finditer(body):
        line_start = body.rfind("\n", 0, m.start()) + 1
        if line_start in heads and not body[line_start : m.start()].strip():
            continue
        num = m.group(2)
        i = bisect_right(offsets, m.start()) - 1
        src = found[i].num if i >= 0 else ""
        if num not in known:
            dangling[f"{m.group(1)} {num}"] += 1
        elif num != src:
            edges[(src, num)] += 1
    return edges, dangling


def duplicates(found: list[Result]) -> dict[str, list[Result]]:
    by_num = defaultdict(list)
    for r in found:
        by_num[r.num].append(r)
    return {n: rs for n, rs in by_num.items() if len(rs) > 1}


def gaps(doc: Text, found: list[Result]) -> dict[str, list[tuple[str, str]]]:
    groups = defaultdict(set)
    for r in found:
        head, _, last = r.num.rpartition(".")
        if head and last.isdigit():
            groups[head].add(int(last))
    equations = set(_EQUATION.findall(doc.body))
    mentioned = {m.group(2) for m in _MENTION.finditer(_blank_brackets(doc.body))}
    out = {}
    for head, nums in sorted(groups.items()):
        missing = []
        for k in range(1, max(nums)):
            if k in nums:
                continue
            num = f"{head}.{k}"
            why = "equation" if num in equations else "referenced" if num in mentioned else ""
            missing.append((num, why))
        if missing:
            out[head] = missing
    return out


def markers(doc: Text) -> list[tuple[str, int, int, str]]:
    rx = {k: re.compile(v, re.I) for k, v in MARKERS.items()}
    hits = []
    for m in re.finditer(r"[^\n]*", doc.body):
        line = m.group()
        if MARK.match(line):
            continue
        for kind, r in rx.items():
            if r.search(line):
                page, n = doc.where(m.start())
                hits.append((kind, page, n + 1, " ".join(line.split())))
    return hits


def _page_start(doc: Text, page: int) -> int | None:
    i = next((j for j, p in enumerate(doc.pages) if p >= page), None)
    return None if i is None else doc.starts[i]


def bibliography(doc: Text, first_page: int) -> dict[str, str]:
    start = _page_start(doc, first_page)
    if start is None:
        return {}
    entries: dict[str, str] = {}
    key = None
    for line in doc.body[start:].splitlines():
        if MARK.match(line):
            continue
        m = _BIB.match(line)
        if m:
            key = m.group(1).strip()
            entries[key] = m.group(2).strip()
        elif key and line.strip():
            entries[key] += " " + line.strip()
    return {k: " ".join(v.split()) for k, v in entries.items()}


def citations(doc: Text, keys: set[str], before: int) -> dict[str, list[int]]:
    end = _page_start(doc, before) if before else None
    end = len(doc.body) if end is None else end
    out = defaultdict(list)
    for m in _BRACKET.finditer(doc.body, 0, end):
        for part in m.group()[1:-1].split(";"):
            key = part.split(",")[0].strip()
            if key in keys:
                out[key].append(doc.where(m.start())[0])
    return dict(out)


def outline(text: str) -> list[tuple[int, str, int | None]]:
    out = []
    for line in text.splitlines():
        m = _OUTLINE.match(line)
        if m:
            depth = len(m.group(1)) // 2
            out.append((depth, m.group(2).strip(), int(m.group(3)) if m.group(3) else None))
    return out


def chapters(
    items: list[tuple[int, str, int | None]], last_page: int
) -> list[tuple[str, int, int]]:
    top = [(t, p) for d, t, p in items if d == 0 and p is not None]
    out = []
    for i, (title, page) in enumerate(top):
        end = top[i + 1][1] if i + 1 < len(top) else last_page + 1
        out.append((title, page, end - page))
    return out


def triage(text: str, outline_text: str = "") -> Triage:
    doc = load(text)
    found = results(doc)
    edges, dangling = cross_refs(doc, found)
    items = outline(outline_text)
    bib_page = next((p for _, t, p in items if t.lower() in ("bibliography", "references")), 0)
    bib = bibliography(doc, bib_page) if bib_page else {}
    return Triage(
        results=found,
        edges=edges,
        dangling=dangling,
        duplicates=duplicates(found),
        gaps=gaps(doc, found),
        markers=markers(doc),
        citations=citations(doc, set(bib), bib_page),
        bibliography=bib,
        chapters=chapters(items, doc.pages[-1] if doc.pages else 0),
    )
