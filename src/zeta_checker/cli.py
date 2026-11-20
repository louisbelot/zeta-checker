from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from zeta_checker import archive, fetch, hatches, imports, lake, pdftext, statements
from zeta_checker.reference import REFERENCES


def table(rows: list, headers: list[str]) -> str:
    numeric = [bool(rows) and all(isinstance(r[i], int) for r in rows) for i in range(len(headers))]
    rows = [[str(c) for c in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    fmt = "  ".join(
        f"{{:{'>' if num else '<'}{w}}}" for num, w in zip(numeric, widths, strict=True)
    )
    lines = [fmt.format(*headers)] + [fmt.format(*r) for r in rows]
    return "\n".join(line.rstrip() for line in lines)


def dump(path: Path | None, body) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def cmd_fetch(args) -> int:
    sources = fetch.load(args.manifest)
    root = args.workspace / "downloads"
    if args.upstream:
        rows = fetch.upstream(sources)
    elif args.rehash:
        rows = fetch.rehash(sources)
    else:
        rows = fetch.sync(sources, root, record=args.record)
        if args.record:
            fetch.save(args.manifest, sources)
    print(
        table(
            [(r.name, r.state, r.size, r.sha256[:16], r.detail) for r in rows],
            ["file", "state", "bytes", "sha256", ""],
        )
    )
    print(f"{sum(r.size for r in rows)} bytes in {len(rows)} files")
    bad = [r for r in rows if r.state in ("changed", "new")]
    return 1 if bad else 0


def cmd_extract(args) -> int:
    paths = archive.parts(args.workspace / "downloads", args.stem)
    with archive.stream(paths) as f:
        packed, unpacked, members = archive.gzip_check(f)
    print(
        f"{len(paths)} parts, {packed} bytes compressed, {unpacked} bytes of tar, "
        f"{members} gzip member{'s' * (members != 1)}"
    )
    if args.list:
        with archive.stream(paths) as f:
            found = archive.listing(f)
    else:
        found = archive.extract(paths, args.workspace / args.into)
        print(f"extracted into {args.workspace / args.into}")
    print(
        f"{found.members} members: {found.files} files, {found.dirs} directories, "
        f"{found.bytes} bytes"
    )
    for label, items in (
        ("unsafe", found.unsafe),
        ("unportable", found.unportable),
        ("colliding", found.collisions),
    ):
        print(f"{label}: {len(items)}")
        for item in items[:20]:
            print(f"  {item}")
    print(table(sorted(found.top.items(), key=lambda kv: -kv[1]), ["top level", "files"]))
    return 0 if found.clean else 1


def cmd_inventory(args) -> int:
    if args.archive is None:
        inv = archive.inventory(args.root, depth=args.depth)
    else:
        paths = archive.parts(args.archive.parent, args.archive.name)
        inv = archive.inventory_pairs(archive.read_members(paths, args.under), args.depth)
    print(f"{inv.files} files, {inv.lines} lines, {inv.bytes} bytes under {args.root}")
    by = lambda t: sorted(t.items(), key=lambda kv: -kv[1][1])  # noqa: E731
    print(table([(k, *v) for k, v in by(inv.by_ext)], ["extension", "files", "lines", "bytes"]))
    print()
    print(table([(k, *v) for k, v in by(inv.by_dir)], ["directory", "files", "lines", "bytes"]))
    print()
    print(table(inv.largest, ["lines", "largest files"]))
    dump(args.json, asdict(inv))
    return 0


def cmd_pdftext(args) -> int:
    out = args.out or args.workspace / "text"
    for pdf in args.pdf:
        doc = pdftext.read(pdf, args.engine)
        written = pdftext.write(doc, out, pdf.stem)
        dump(out / f"{pdf.stem}.meta.json", doc.meta | {"engine": doc.engine})
        chars = sum(len(p) for p in doc.pages)
        print(
            f"{pdf.name}: {len(doc.pages)} pages, {chars} characters, "
            f"{len(doc.outline)} outline entries ({doc.engine})"
        )
        for path in written:
            print(f"  {path}")
    return 0


def cmd_find(args) -> int:
    hits = pdftext.find(args.text.read_text(encoding="utf-8"), args.pattern)
    for page, line, text in hits[: args.limit]:
        print(f"p{page}:{line}: {text}")
    print(f"{len(hits)} matching lines")
    return 0


def cmd_config(args) -> int:
    lk = lake.load(args.root)
    print(f"toolchain: {lk.toolchain}")
    print(f"lakefile: {lk.lakefile}")
    for note in lk.notes:
        print(f"note: {note}")
    print()
    print(
        table(
            [(p["name"], p["lakefile"], p["manifest"], p["match"]) for p in lake.pins(lk)],
            ["require", "lakefile rev", "manifest rev", "same"],
        )
    )
    print()
    pk = lake.packages(lk)
    print(
        table(
            [(p["name"], p["rev"], p["inputRev"], p["inherited"], p["url"]) for p in pk],
            ["package", "rev", "inputRev", "inherited", "url"],
        )
    )
    print()
    print("arguments and options:")
    for row in lake.arguments(lk):
        print(f"  {row}")
    found = lake.native(lk)
    print(f"native code keys: {found or 'none'}")
    cov = lake.coverage(lk)
    print()
    print(f"modules under srcDir: {cov['modules']}")
    print(table(sorted(cov["per_lib"].items()), ["lean_lib", "modules"]))
    print(f"libs outside defaultTargets: {cov['not_default'] or 'none'}")
    print(f"modules matched by no lib: {len(cov['unmatched'])}")
    for mod in cov["unmatched"][:20]:
        print(f"  {mod}")
    print(f"modules matched by more than one lib: {cov['multiple']}")
    stray = lake.stray_files(args.root)
    print(f"files other than .lean and Lake config: {len(stray)}")
    for rel, kind in stray[:20]:
        print(f"  {kind:>14}  {rel}")
    dump(
        args.json,
        {
            "toolchain": lk.toolchain,
            "lakefile": lk.lakefile,
            "notes": lk.notes,
            "pins": lake.pins(lk),
            "packages": pk,
            "arguments": lake.arguments(lk),
            "native": found,
            "coverage": cov,
            "stray": stray,
        },
    )
    return 0


def sources(args):
    if args.archive is None:
        return hatches.read(args.root)
    paths = archive.parts(args.archive.parent, args.archive.name)
    pairs = archive.read_members(paths, args.under, ".lean")
    return ((rel, data) for rel, data in pairs if not hatches.SKIP_DIRS & set(rel.split("/")[:-1]))


def cmd_scan(args) -> int:
    label = (args.archive or args.root).as_posix()
    report = hatches.scan_pairs(label, sources(args))
    print(f"{report.files} files, {report.lines} lines, {report.bytes} bytes scanned")
    if report.bad_utf8:
        print(f"not valid UTF-8: {len(report.bad_utf8)}")
    rows = report.counts()
    print(table(rows, ["risk", "group", "rule", "hits", "files"]) if rows else "no hits")
    keep = hatches.RISKS[: hatches.RISKS.index(args.risk) + 1]
    for risk, _, rule, _, _ in rows:
        if risk not in keep:
            continue
        sample = [h for h in report.hits if h.rule == rule and h.risk == risk][: args.show]
        print(f"\n[{risk}] {rule}")
        for h in sample:
            print(f"  {h.file}:{h.line}  {h.text}")
    dump(args.json, report.as_dict())
    return 0


def _modules(lk: lake.Lake, wanted: list[str] | None) -> list[str]:
    if wanted:
        return wanted
    out = []
    for lib in lk.config.get("lean_lib", []):
        if "globs" not in lib and "roots" in lib:
            out.extend(lib["roots"])
    return out


def cmd_statements(args) -> int:
    lk = lake.load(args.root)
    src = args.root / lk.config.get("srcDir", ".")
    parsed = []
    for name in _modules(lk, args.module):
        path = src / Path(*name.split(".")).with_suffix(".lean")
        rel = path.relative_to(args.root).as_posix()
        parsed.append(statements.parse(path.read_text(encoding="utf-8"), rel))
    defs = {d.full: d for m in parsed for d in m.decls if d.kind in ("def", "abbrev")}
    wanted: set[str] = set()
    body = {"modules": [], "theorems": []}
    for m in parsed:
        print(f"{m.file}")
        print(f"  imports: {', '.join(m.imports) or 'none'}")
        print(f"  open: {'; '.join(m.opens) or 'none'}")
        for d in m.decls:
            proof = f" := {d.body[:160]}" if d.body else ""
            print(f"  {d.file}:{d.line}  {d.signature}{proof}")
        body["modules"].append(asdict(m))
    print()
    for d in (d for m in parsed for d in m.decls if d.kind in ("theorem", "lemma", "example")):
        stmt = statements.statement(d)
        target = defs.get(stmt)
        expr = target.body if target else stmt
        items = statements.shape(expr)
        found = statements.names(expr, statements.bound_names(items))
        wanted.update(n for n in found + statements.names(stmt) if not n.startswith("."))
        entry = {"decl": d.full, "statement": stmt, "shape": items, "names": found}
        print(f"{d.full}  ({d.file}:{d.line})")
        if target:
            print(f"  statement unfolds {target.full} ({target.file}:{target.line})")
            entry["unfolds"] = target.full
        for kind, text in items:
            print(f"  {kind:<10} {text}")
        print(f"  names: {', '.join(found)}")
        ref = REFERENCES.get(stmt) if target is None else None
        if ref is not None:
            print(f"  this is {ref.name} itself: {ref.repo}@{ref.rev[:12]} {ref.path}:{ref.line}")
            items = statements.shape(ref.statement)
            ref_names = statements.names(ref.statement, statements.bound_names(items))
            wanted.update(n for n in ref_names if not n.startswith("."))
        elif "riemannZeta" in found:
            ref = REFERENCES["RiemannHypothesis"]
            print(f"  against {ref.name} ({ref.repo}@{ref.rev[:12]} {ref.path}:{ref.line})")
            rows = statements.compare(expr, ref.statement)
            for kind, ours, theirs, verdict in rows:
                print(f"    {kind:<10} {verdict}")
                if verdict != "same":
                    print(f"      here:    {ours}")
                    print(f"      mathlib: {theirs}")
            entry["against"] = {"reference": asdict(ref), "rows": rows}
        body["theorems"].append(entry)
        print()
    if args.trace:
        declared, overrides, n = statements.trace(sources(args), wanted)
        print(f"names traced through {n} files: {', '.join(sorted(wanted))}")
        print(f"declarations with one of these names: {len(declared)}")
        for rel, line, kind, name in declared:
            print(f"  {rel}:{line}  {kind} {name}")
        print(f"notation, syntax or macros mentioning them: {len(overrides)}")
        for rel, line, kind, text in overrides:
            print(f"  {rel}:{line}  {kind} {text}")
        body["trace"] = {"names": sorted(wanted), "declared": declared, "overrides": overrides}
    dump(args.json, body)
    return 0


def cmd_imports(args) -> int:
    lk = lake.load(args.root)
    src_dir = lk.config.get("srcDir", ".")
    g = imports.build_pairs(sources(args), src_dir)
    roots = args.roots or _modules(lk, None)
    cone = g.cone(roots)
    packages = imports.package_roots(lk.manifest)
    n, lines, size = g.totals(g.imports)
    c_n, c_lines, c_size = g.totals(cone)
    print(f"{n} modules, {lines} lines, {size} bytes under {src_dir}")
    print(f"import cone of {', '.join(roots)}: {c_n} modules, {c_lines} lines, {c_size} bytes")
    print(f"outside the cone: {n - c_n} modules, {lines - c_lines} lines")
    edges = sum(len(v) for v in g.imports.values())
    print(f"import edges: {edges}")
    print(table(g.external().most_common(), ["external root", "imports"]))
    shadow = g.shadowing(packages)
    print(f"project modules named like a dependency or Lean core: {len(shadow)}")
    for mod in shadow[:20]:
        print(f"  {mod}")
    bad = g.unresolved(packages)
    print(f"imports matching no project module and no dependency: {len(bad)}")
    for mod, dep in bad[:20]:
        print(f"  {mod} imports {dep}")
    print(f"files starting with a license or copyright header: {len(g.headers)}")
    body = {
        "roots": roots,
        "cone": sorted(cone),
        "external": dict(g.external()),
        "shadowing": shadow,
        "unresolved": bad,
        "headers": g.headers,
    }
    if args.hatches:
        hits = json.loads(args.hatches.read_text(encoding="utf-8"))["hits"]
        rows = {}
        for h in hits:
            key = (h["risk"], h["rule"])
            inside = imports.module_of(h["file"], src_dir) in cone
            row = rows.setdefault(key, [0, 0, set(), set()])
            row[0] += 1
            row[1] += inside
            row[2].add(h["file"])
            if inside:
                row[3].add(h["file"])
        order = {r: i for i, r in enumerate(hatches.RISKS)}
        ranked = sorted(rows.items(), key=lambda kv: (order[kv[0][0]], -kv[1][0]))
        print()
        print(
            table(
                [(r, rule, v[0], v[1], len(v[2]), len(v[3])) for (r, rule), v in ranked],
                ["risk", "rule", "hits", "in cone", "files", "in cone"],
            )
        )
        body["hatches"] = {f"{r} {rule}": v[:2] for (r, rule), v in ranked}
    dump(args.json, body)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="zeta-checker")
    p.add_argument(
        "-w",
        "--workspace",
        type=Path,
        default=Path(os.environ.get("ZETA_CHECKER_WORKSPACE", "workspace")),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch", help="download the sources and check them against the manifest")
    s.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    s.add_argument("--record", action="store_true", help="store hashes of new files")
    s.add_argument("--upstream", action="store_true", help="compare server headers only")
    s.add_argument("--rehash", action="store_true", help="hash the remote files again")
    s.set_defaults(run=cmd_fetch)

    s = sub.add_parser("extract", help="check the split tarball and extract it")
    s.add_argument("--stem", default="lean.tar.gz")
    s.add_argument("--into", default="alpoge_lean")
    s.add_argument("--list", action="store_true", help="check members without extracting")
    s.set_defaults(run=cmd_extract)

    s = sub.add_parser("inventory", help="files, lines and bytes by extension and directory")
    s.add_argument("root", type=Path)
    s.add_argument("--depth", type=int, default=2)
    s.add_argument("--json", type=Path)
    s.add_argument("--archive", type=Path, help="read files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the tree")
    s.set_defaults(run=cmd_inventory)

    s = sub.add_parser("pdftext", help="page-numbered text and outline of PDFs")
    s.add_argument("pdf", type=Path, nargs="+")
    s.add_argument("--engine", choices=["auto", "pypdf", "pdftotext"], default="auto")
    s.add_argument("--out", type=Path)
    s.set_defaults(run=cmd_pdftext)

    s = sub.add_parser("find", help="search extracted text, printing page numbers")
    s.add_argument("text", type=Path)
    s.add_argument("pattern")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(run=cmd_find)

    s = sub.add_parser("config", help="toolchain, dependencies and Lake options")
    s.add_argument("root", type=Path)
    s.add_argument("--json", type=Path)
    s.set_defaults(run=cmd_config)

    s = sub.add_parser("scan", help="escape hatches in Lean sources")
    s.add_argument("root", type=Path)
    s.add_argument("--json", type=Path)
    s.add_argument("--show", type=int, default=5)
    s.add_argument("--risk", choices=hatches.RISKS, default="medium")
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_scan)

    s = sub.add_parser("statements", help="top-level statements, traced to their definitions")
    s.add_argument("root", type=Path)
    s.add_argument("--module", action="append")
    s.add_argument("--json", type=Path)
    s.add_argument("--no-trace", dest="trace", action="store_false")
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_statements)

    s = sub.add_parser("imports", help="import graph and the cone of the statement modules")
    s.add_argument("root", type=Path)
    s.add_argument("--roots", nargs="+")
    s.add_argument("--hatches", type=Path, help="scan JSON to split by cone")
    s.add_argument("--json", type=Path)
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_imports)

    args = p.parse_args(argv)
    return args.run(args)
