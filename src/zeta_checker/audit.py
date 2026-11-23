from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from zeta_checker import hatches, imports, lake, statements
from zeta_checker.reference import REFERENCES

SCHEMA = 1
SEVERITIES = ("critical", "high", "medium", "low", "info")
OFF = {"false", "0"}
ABSURD = {("False",), ("⊥",), ("¬", "True")}

Pairs = Callable[[], Iterable[tuple[str, bytes]]]


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    file: str
    line: int
    detail: str


@dataclass
class Theorem:
    decl: str
    file: str
    line: int
    statement: str
    shape: list[tuple[str, str]]
    names: list[str]
    unfolds: str = ""
    scope: str = ""
    reference: str = ""
    exact: bool = False
    rows: list[tuple[str, str, str, str]] = field(default_factory=list)


def theorems(root: Path, lk: lake.Lake, modules: list[str]):
    src = root / lk.config.get("srcDir", ".")
    parsed = []
    for name in modules:
        path = src / Path(*name.split(".")).with_suffix(".lean")
        rel = path.relative_to(root).as_posix()
        parsed.append(statements.parse(path.read_text(encoding="utf-8"), rel))
    defs = {d.full: d for m in parsed for d in m.decls if d.kind in ("def", "abbrev")}
    out, wanted = [], set()
    for d in (d for m in parsed for d in m.decls if d.kind in ("theorem", "lemma", "example")):
        stmt = statements.statement(d)
        target = defs.get(stmt)
        expr = target.body if target else stmt
        items = statements.shape(expr)
        found = statements.names(expr, statements.bound_names(items))
        wanted.update(n for n in found + statements.names(stmt) if not n.startswith("."))
        t = Theorem(d.full, d.file, d.line, stmt, items, found)
        if target:
            t.unfolds, t.scope = target.full, target.file
        else:
            t.scope = d.file
        ref = REFERENCES.get(stmt) if target is None else None
        if ref is not None:
            t.reference, t.exact = ref.name, True
            ref_items = statements.shape(ref.statement)
            ref_names = statements.names(ref.statement, statements.bound_names(ref_items))
            wanted.update(n for n in ref_names if not n.startswith("."))
        elif "riemannZeta" in found:
            ref = REFERENCES["RiemannHypothesis"]
            t.reference = ref.name
            t.rows = statements.compare(expr, ref.statement)
        elif items[-1][1] in REFERENCES:
            t.reference = items[-1][1]
            t.rows = [(k, x, "", "only here") for k, x in items[:-1]]
        out.append(t)
    return parsed, out, wanted


def last(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def hypothesis_type(kind: str, text: str) -> str:
    if kind == "premise":
        return text
    inner = text.strip("()[]{}⦃⦄ ")
    return inner.split(":", 1)[1].strip() if ":" in inner else ""


def hypotheses(t: Theorem, props: set[str], project: dict[str, str]) -> list[Finding]:
    conclusion = next((x for k, x in t.shape if k == "conclusion"), "")
    goal = tuple(statements.tokens(conclusion))
    out = []
    for kind, text in t.shape:
        typ = hypothesis_type(kind, text)
        if not typ:
            continue
        toks = tuple(statements.tokens(statements.strip_parens(typ)))
        if toks in ABSURD:
            out.append(
                Finding("critical", "vacuous-hypothesis", t.file, t.line, f"{t.decl}: {text}")
            )
        elif toks == goal or (len(toks) == 1 and toks[0] in props):
            out.append(
                Finding("critical", "circular-hypothesis", t.file, t.line, f"{t.decl}: {text}")
            )
        else:
            local = [n for n in statements.names(typ) if last(n) in project]
            for n in local:
                detail = f"{t.decl}: {text} uses {n}, declared at {project[last(n)]}"
                out.append(Finding("high", "hypothesis-project-name", t.file, t.line, detail))
            if kind == "premise" and not local:
                out.append(Finding("info", "hypothesis", t.file, t.line, f"{t.decl}: {text}"))
    return out


def config_findings(lk: lake.Lake) -> list[Finding]:
    out = []
    lakefile = lk.lakefile or "lakefile"
    if any(n.startswith("lakefile.lean") for n in lk.notes):
        out.append(Finding("high", "lakefile-lean", "lakefile.lean", 0, "Lake runs it as code"))
    if lk.toolchain is None or not lake.OFFICIAL.match(lk.toolchain):
        out.append(Finding("high", "toolchain", "lean-toolchain", 0, str(lk.toolchain)))
    for row in lake.native(lk):
        out.append(Finding("high", "native-code", lakefile, 0, row))
    for pin in lake.pins(lk):
        if not pin["match"]:
            detail = f"{pin['name']}: lakefile {pin['lakefile']}, manifest {pin['manifest']}"
            out.append(Finding("medium", "pin-mismatch", lakefile, 0, detail))
    for where, name, value in lake.options(lk):
        _, risk = hatches.option_risk(name)
        if risk in ("critical", "high", "medium") and value.lower() not in OFF:
            detail = f"{where}: {name} = {value}"
            out.append(Finding(risk, f"lake-option {name}", lakefile, 0, detail))
    return out


def run(root: Path, pairs: Pairs, modules: list[str] | None = None) -> dict:
    lk = lake.load(root)
    src_dir = lk.config.get("srcDir", ".")
    modules = modules or lake.roots(lk)
    findings = config_findings(lk)
    if not modules:
        findings.append(Finding("high", "no-roots", lk.lakefile or "", 0, "no lean_lib roots"))
    parsed, thms, wanted = theorems(root, lk, modules)

    graph = imports.build_pairs(pairs(), src_dir)
    cone = graph.cone(modules)
    packages = imports.package_roots(lk.manifest)
    for mod in graph.shadowing(packages):
        findings.append(Finding("high", "module-shadows-dependency", mod, 0, mod))
    for mod, dep in graph.unresolved(packages):
        findings.append(Finding("medium", "unresolved-import", mod, 0, dep))

    report = hatches.scan_pairs(root.as_posix(), pairs())
    below = Counter()
    for h in report.hits:
        inside = imports.module_of(h.file, src_dir) in cone
        value = h.name.split()[-1].lower() if h.rule.startswith("set_option ") else ""
        if inside and value in OFF:
            below[f"{h.rule} {value}"] += 1
        elif inside and h.risk == "low":
            below[h.rule] += 1
        elif inside:
            findings.append(Finding(h.risk, f"hatch {h.rule}", h.file, h.line, h.text))
        elif value not in OFF:
            detail = f"outside the import cone: {h.text}"
            findings.append(Finding("low", f"hatch {h.rule}", h.file, h.line, detail))

    declared, overrides, _ = statements.trace(pairs(), wanted) if wanted else ([], [], 0)
    cones: dict[str, set[str]] = {}

    def sees(scope: str, rel: str) -> bool:
        if scope not in cones:
            cones[scope] = graph.cone([imports.module_of(scope, src_dir)])
        return imports.module_of(rel, src_dir) in cones[scope]

    uses: dict[str, set[str]] = {}
    for t in thms:
        for n in statements.names(t.statement):
            uses.setdefault(last(n), set()).add(t.file)
        for n in t.names:
            uses.setdefault(last(n), set()).add(t.scope)
    scopes = {t.file for t in thms} | {t.scope for t in thms}
    root_decls = {(d.file, d.line) for m in parsed for d in m.decls}
    for rel, line, kind, name in declared:
        if (rel, line) in root_decls:
            continue
        seen = any(sees(scope, rel) for scope in uses.get(last(name), ()))
        note = "" if seen else " (not imported where the statement is elaborated)"
        findings.append(
            Finding(
                "high" if seen else "low",
                "declares-statement-name",
                rel,
                line,
                f"{kind} {name}{note}",
            )
        )
    for rel, line, kind, text in overrides:
        seen = rel in scopes or any(sees(scope, rel) for scope in scopes)
        note = "" if seen else " (not imported where the statement is elaborated)"
        findings.append(
            Finding(
                "high" if seen else "low",
                "notation-on-statement-name",
                rel,
                line,
                f"{kind} {text}{note}",
            )
        )

    props = {t.unfolds for t in thms if t.unfolds} | set(REFERENCES)
    for t in thms:
        project = {last(n): f"{rel}:{line}" for rel, line, _, n in declared if sees(t.scope, rel)}
        findings += hypotheses(t, props, project)
        for kind, _, _, diff in (r for r in t.rows if r[3] != "same"):
            detail = f"{t.decl} vs {t.reference}: {kind}: {diff or 'differs'}"
            findings.append(Finding("medium", "statement-differs", t.file, t.line, detail))
    if not any(t.reference for t in thms):
        where = ", ".join(modules) or "no modules"
        findings.append(Finding("high", "no-rh-statement", where, 0, "no theorem states RH"))

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings = sorted(findings, key=lambda f: (order[f.severity], f.code, f.file, f.line, f.detail))
    n, lines, size = graph.totals(graph.imports)
    c_n, c_lines, _ = graph.totals(cone)
    return {
        "schema": SCHEMA,
        "root": root.name,
        "toolchain": lk.toolchain,
        "lakefile": lk.lakefile,
        "modules": modules,
        "sources": {"modules": n, "lines": lines, "bytes": size},
        "cone": {"modules": c_n, "lines": c_lines},
        "theorems": [asdict(t) for t in thms],
        "severity": {s: sum(f.severity == s for f in findings) for s in SEVERITIES},
        "findings": [asdict(f) for f in findings],
        "low_in_cone": dict(sorted(below.items())),
    }


def worst(report: dict) -> str | None:
    return next((s for s in SEVERITIES if report["severity"][s]), None)
