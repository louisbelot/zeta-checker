from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

from zeta_checker import fs
from zeta_checker.leanlex import ID_REST, IDENT, Lines, ident_after, ident_before, mask

RISKS = ("critical", "high", "medium", "low")

WORDS = {
    "sorry": ("unproven", "critical"),
    "admit": ("unproven", "critical"),
    "stop": ("unproven", "critical"),
    "sorryAx": ("unproven", "critical"),
    "mkSorry": ("unproven", "critical"),
    "mkLabeledSorry": ("unproven", "critical"),
    "admitGoal": ("unproven", "critical"),
    "axiom": ("axioms", "critical"),
    "skipKernelTC": ("kernel", "critical"),
    "addDeclWithoutChecking": ("kernel", "critical"),
    "addDecl": ("kernel", "high"),
    "addDeclCore": ("kernel", "high"),
    "modifyEnv": ("kernel", "high"),
    "setEnv": ("kernel", "high"),
    "addAndCompile": ("kernel", "medium"),
    "native_decide": ("compiler", "high"),
    "native": ("compiler", "high"),
    "ofReduceBool": ("compiler", "high"),
    "ofReduceNat": ("compiler", "high"),
    "reduceBool": ("compiler", "high"),
    "reduceNat": ("compiler", "high"),
    "trustCompiler": ("compiler", "high"),
    "implemented_by": ("compiler", "high"),
    "extern": ("compiler", "high"),
    "csimp": ("compiler", "high"),
    "opaque": ("unchecked", "medium"),
    "unsafe": ("unchecked", "medium"),
    "partial": ("unchecked", "low"),
    "unsafeCast": ("unchecked", "medium"),
    "unsafeBaseIO": ("unchecked", "medium"),
    "unsafeIO": ("unchecked", "medium"),
    "unsafeEIO": ("unchecked", "medium"),
    "macro_rules": ("meta", "medium"),
    "elab_rules": ("meta", "medium"),
    "elab": ("meta", "medium"),
    "macro": ("meta", "low"),
    "syntax": ("meta", "low"),
    "declare_syntax_cat": ("meta", "low"),
    "notation": ("meta", "low"),
    "notation3": ("meta", "low"),
    "infix": ("meta", "low"),
    "infixl": ("meta", "low"),
    "infixr": ("meta", "low"),
    "prefix": ("meta", "low"),
    "postfix": ("meta", "low"),
    "run_cmd": ("exec", "medium"),
    "run_elab": ("exec", "medium"),
    "run_meta": ("exec", "medium"),
    "run_tac": ("exec", "medium"),
    "#eval": ("exec", "medium"),
    "#eval!": ("exec", "medium"),
    "initialize": ("exec", "medium"),
    "builtin_initialize": ("exec", "medium"),
    "Process": ("exec", "high"),
    "set_option": ("options", "low"),
    "#exit": ("info", "low"),
}

ATTRIBUTE_ONLY = {"implemented_by", "extern", "csimp"}
KEYWORDS = {"sorry", "admit", "stop", "axiom", "opaque", "unsafe", "partial"}
NO_LITERAL = {"meta", "exec", "options", "info", "unchecked"}

_WORDS = "|".join(sorted((re.escape(w) for w in WORDS), key=len, reverse=True))
TRIGGER = re.compile(rf"(?<![{ID_REST}])({_WORDS})(?![{ID_REST}])")
_OPTION = re.compile(rf"\s+({IDENT})\s+(\S+)")
_DECLNAME = re.compile(
    rf"\s+(?:(?:def|theorem|instance|inductive|structure|class|abbrev)\s+)?({IDENT})"
)
_NATIVE_SET = re.compile(r"\s*:=\s*true\b")
_IMPORT = re.compile(
    rf"^[ \t]*(?:(?:public|private)[ \t]+)?(?:meta[ \t]+)?import[ \t]+(?:all[ \t]+)?"
    rf"(Lean(?:\.{IDENT})?)(?![{ID_REST}.])",
    re.M,
)


@dataclass
class Hit:
    rule: str
    group: str
    risk: str
    file: str
    line: int
    name: str
    text: str


def option_risk(name: str) -> tuple[str, str]:
    if name == "debug.skipKernelTC":
        return "kernel", "critical"
    if name.startswith("debug.") or name == "allowUnsafeReducibility":
        return "options", "high"
    if name in ("autoImplicit", "relaxedAutoImplicit"):
        return "options", "medium"
    return "options", "low"


def _in_attribute(text: str, p: int, reach: int = 400) -> bool:
    depth = 0
    for i in range(p - 1, max(p - reach, 0) - 1, -1):
        ch = text[i]
        if ch == "]":
            depth += 1
        elif ch == "[":
            if depth:
                depth -= 1
                continue
            head = text[max(i - 12, 0) : i].rstrip()
            return head.endswith("@") or re.search(r"(?<![\w.])attribute$", head) is not None
    return False


def classify(text: str, m: re.Match) -> tuple[str, str, str, str] | None:
    word = m.group(1)
    p, q = m.span(1)
    group, risk = WORDS[word]
    start = ident_before(text, p)
    full = text[start : ident_after(text, q)]
    before = text[start - 1] if start else ""
    if before == "«" and text.startswith("»", q):
        if word in KEYWORDS:
            return ("escaped-name", "info", "low", word)
        start, full = p, word
    elif before == "`":
        return (f"name-literal {word}", "meta", "high", full) if group not in NO_LITERAL else None
    if start < p:
        if word == "admit":
            return ("MVarId.admit", "unproven", "critical", full)
        if word in KEYWORDS or group == "meta":
            return None
    if word == "skipKernelTC" and re.search(r"set_option\s+$", text[max(start - 40, 0) : start]):
        return None
    if word == "Process":
        return (word, group, risk, full) if full.startswith(("IO.Process.", "Process.")) else None
    if word == "native":
        prev = text[max(p - 2, 0) : p].rstrip()
        if prev.endswith("+") or _NATIVE_SET.match(text, q):
            return ("decide +native", group, risk, full)
        return None
    if word in ATTRIBUTE_ONLY:
        return (word, group, risk, full) if _in_attribute(text, start) else None
    if word == "set_option":
        o = _OPTION.match(text, q)
        if o is None:
            return None
        group, risk = option_risk(o.group(1))
        return (f"set_option {o.group(1)}", group, risk, f"{o.group(1)} {o.group(2)}")
    if word in ("axiom", "opaque", "unsafe", "partial"):
        d = _DECLNAME.match(text, q)
        return (word, group, risk, d.group(1) if d else "")
    return (word, group, risk, full)


def scan_source(src: str, rel: str) -> list[Hit]:
    if not TRIGGER.search(src) and "import Lean" not in src:
        return []
    masked = mask(src)
    text = masked.text
    lines = Lines(src)
    hits = []
    for m in TRIGGER.finditer(text):
        c = classify(text, m)
        if c is None:
            continue
        rule, group, risk, name = c
        n = lines.line(m.start(1))
        hits.append(Hit(rule, group, risk, rel, n, name, lines.text(n).strip()[:200]))
    for m in _IMPORT.finditer(text):
        n = lines.line(m.start())
        hits.append(Hit("import Lean", "meta", "low", rel, n, m.group(1), m.group().strip()))
    for offset, what in masked.flags:
        n = lines.line(offset)
        hits.append(Hit(what, "info", "low", rel, n, "", lines.text(n).strip()[:200]))
    return hits


SKIP_DIRS = {".lake", ".git", "lake-packages", "build"}


def lean_files(root: Path) -> list[Path]:
    return list(fs.walk(root, SKIP_DIRS, ".lean"))


def relative(root: Path, files: list[Path] | None = None) -> list[tuple[str, Path]]:
    base = fs.long(root)
    paths = lean_files(root) if files is None else [fs.long(p) for p in files]
    return [(p.relative_to(base).as_posix(), p) for p in paths]


def read(root: Path, files: list[Path] | None = None) -> Iterator[tuple[str, bytes]]:
    for rel, path in relative(root, files):
        yield rel, path.read_bytes()


@dataclass
class Report:
    root: str
    files: int
    lines: int
    bytes: int
    bad_utf8: list[str]
    hits: list[Hit]

    def counts(self) -> list[tuple[str, str, str, int, int]]:
        hits = Counter((h.risk, h.group, h.rule) for h in self.hits)
        files = Counter()
        for key in {(h.risk, h.group, h.rule, h.file) for h in self.hits}:
            files[key[:3]] += 1
        order = {r: i for i, r in enumerate(RISKS)}
        rows = [(r, g, rule, n, files[(r, g, rule)]) for (r, g, rule), n in hits.items()]
        return sorted(rows, key=lambda row: (order[row[0]], -row[3], row[2]))

    def as_dict(self) -> dict:
        body = asdict(self)
        body["counts"] = self.counts()
        return body


def scan(root: Path, files: list[Path] | None = None) -> Report:
    return scan_pairs(root.as_posix(), read(root, files))


def scan_pairs(label: str, pairs: Iterable[tuple[str, bytes]]) -> Report:
    hits, bad, count, lines, size = [], [], 0, 0, 0
    for rel, data in pairs:
        try:
            src = data.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(rel)
            src = data.decode("utf-8", errors="replace")
        count += 1
        size += len(data)
        lines += src.count("\n") + (1 if src and not src.endswith("\n") else 0)
        hits.extend(scan_source(src, rel))
    return Report(label, count, lines, size, bad, hits)
