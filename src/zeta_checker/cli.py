from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import mpmath

from zeta_checker import (
    archive,
    audit,
    criteria,
    declgraph,
    enclose,
    fetch,
    forms,
    hatches,
    imports,
    lake,
    li,
    manuscript,
    pdftext,
    statements,
    zeros,
)
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
        rows = fetch.upstream(sources) + fetch.next_parts(sources)
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
    files = [r for r in rows if r.state != "absent"]
    print(f"{sum(r.size for r in files)} bytes in {len(files)} files")
    bad = [r for r in rows if r.state in ("changed", "new")]
    return 1 if bad else 0


def cmd_extract(args) -> int:
    paths = archive.parts(args.workspace / "downloads", args.stem)
    with archive.stream(paths) as f:
        size, digest = fetch.digest(f)
    known = fetch.joined(args.manifest).get(args.stem)
    if known is None:
        state = "recorded" if args.record else "not in the manifest"
        if args.record:
            fetch.record_joined(args.manifest, args.stem, len(paths), size, digest)
    elif known == {"parts": len(paths), "size": size, "sha256": digest}:
        state = "matches the manifest"
    else:
        state = f"differs from the manifest: {known}"
    print(f"joined {args.stem}: {size} bytes, sha256 {digest} ({state})")
    if state.startswith("differs"):
        return 1
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


def cmd_manuscript(args) -> int:
    outline = args.text.with_name(args.text.name.removesuffix(".txt") + ".outline.txt")
    tr = manuscript.triage(
        args.text.read_text(encoding="utf-8"),
        outline.read_text(encoding="utf-8") if outline.exists() else "",
    )
    if tr.chapters:
        print(table([(t, p, n) for t, p, n in tr.chapters], ["part", "page", "pages"]))
        print()
    kinds = Counter(r.kind for r in tr.results)
    print(f"numbered results: {len(tr.results)}")
    print(table(kinds.most_common(), ["kind", "count"]))
    if args.index:
        for r in tr.results:
            title = f" ({r.title})" if r.title else ""
            print(f"  p{r.page}  {r.label}{title}")
    labels = {r.num: r for r in tr.results}
    refs = sum(tr.edges.values())
    print(f"\ncross-references between numbered results: {refs} ({len(tr.edges)} distinct pairs)")
    rows = [
        (labels[n].label, labels[n].page, k, labels[n].title[:60])
        for n, k in tr.indegree().most_common(args.top)
    ]
    print(table(rows, ["most referenced", "page", "from", "title"]))
    internal = {k: v for k, v in tr.dangling.items() if k.split()[1].count(".") >= 2}
    print(f"\nreferences to numbers with no header: {sum(tr.dangling.values())}")
    print(f"  of those, numbered with at least three parts: {len(internal)}")
    for k, v in sorted(internal.items()):
        print(f"    {k}  x{v}")
    print(f"numbers used by two headers: {len(tr.duplicates)}")
    for num, rs in tr.duplicates.items():
        print(f"  {num}: " + ", ".join(f"{r.kind} p{r.page}" for r in rs))
    missing = [(n, why) for v in tr.gaps.values() for n, why in v]
    print(f"gaps in the numbering: {len(missing)}")
    for n, why in missing:
        print(f"  {n}  {why or 'not found anywhere'}")
    print(f"\nmarkers: {len(tr.markers)}")
    for kind, page, line, text in tr.markers:
        print(f"  p{page}:{line} [{kind}] {text[:140]}")
    cited = sorted(tr.citations.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(v) for v in tr.citations.values())
    print(f"\nbibliography: {len(tr.bibliography)} entries, {len(cited)} cited, {total} citations")
    rows = [(k, len(v), len(set(v)), tr.bibliography[k][:70]) for k, v in cited[: args.top]]
    print(table(rows, ["key", "cites", "pages", "entry"]))
    never = sorted(set(tr.bibliography) - set(tr.citations))
    print(f"entries never cited in brackets: {len(never)}")
    dump(args.json, tr.as_dict())
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


def cmd_statements(args) -> int:
    lk = lake.load(args.root)
    src = args.root / lk.config.get("srcDir", ".")
    parsed, thms, wanted = audit.theorems(args.root, lk, args.module or lake.roots(lk))
    body = {"modules": [], "theorems": []}
    for m in parsed:
        print(f"{m.file}")
        print(f"  imports: {', '.join(m.imports) or 'none'}")
        print(f"  open: {'; '.join(m.opens) or 'none'}")
        own = [i for i in m.imports if (src / Path(*i.split("."))).with_suffix(".lean").exists()]
        print(f"  project imports: {', '.join(own) or 'none'}")
        ctx = statements.context((args.root / m.file).read_text(encoding="utf-8"))
        print(f"  instance, attribute, option, notation or open commands: {len(ctx)}")
        for line, _, text in ctx:
            print(f"    {m.file}:{line}  {text[:120]}")
        for d in m.decls:
            proof = f" := {d.body[:160]}" if d.body else ""
            print(f"  {d.file}:{d.line}  {d.signature}{proof}")
        mod = asdict(m)
        for d in mod["decls"]:
            del d["raw"]
        body["modules"].append(mod)
    print()
    for t in thms:
        print(f"{t.decl}  ({t.file}:{t.line})")
        if t.unfolds:
            print(f"  statement unfolds {t.unfolds}")
        for kind, text in t.shape:
            print(f"  {kind:<10} {text}")
        print(f"  names: {', '.join(t.names)}")
        ref = REFERENCES.get(t.reference)
        if t.exact:
            print(f"  this is {ref.name} itself: {ref.repo}@{ref.rev[:12]} {ref.path}:{ref.line}")
        elif ref is not None:
            print(f"  against {ref.name} ({ref.repo}@{ref.rev[:12]} {ref.path}:{ref.line})")
            for kind, ours, theirs, verdict in t.rows:
                print(f"    {kind:<10} {verdict}")
                if verdict != "same":
                    print(f"      here:    {ours}")
                    print(f"      mathlib: {theirs}")
        body["theorems"].append(asdict(t))
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


def cmd_audit(args) -> int:
    report = audit.run(args.root, lambda: sources(args), args.module)
    print(f"{report['root']}: {report['toolchain']}, {report['lakefile']}")
    src, cone = report["sources"], report["cone"]
    print(f"{src['modules']} modules, {src['lines']} lines; cone of {', '.join(report['modules'])}")
    print(f"  {cone['modules']} modules, {cone['lines']} lines")
    print(table([(s, n) for s, n in report["severity"].items()], ["severity", "findings"]))
    keep = audit.SEVERITIES[: audit.SEVERITIES.index(args.severity) + 1]
    for f in report["findings"]:
        if f["severity"] in keep:
            at = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            print(f"[{f['severity']}] {f['code']}  {at}  {f['detail'][:160]}")
    if report["low_in_cone"]:
        print("low-risk hits inside the cone, counted only:")
        print(table(sorted(report["low_in_cone"].items(), key=lambda kv: -kv[1]), ["rule", "hits"]))
    dump(args.json, report)
    worst = audit.worst(report)
    return 2 if worst == "critical" else 1 if worst == "high" else 0


def cmd_decls(args) -> int:
    lk = lake.load(args.root)
    src_dir = lk.config.get("srcDir", ".")
    roots = set(args.roots or lake.roots(lk))
    g = declgraph.build(lambda: sources(args))
    edges = len(g.targets)
    kinds = Counter(g.kinds)
    anonymous = sum(1 for n in g.names if "<instance " in n)
    print(f"{len(g)} declarations in {len(g.paths)} files, {edges} name references resolved")
    print(table(kinds.most_common(), ["kind", "count"]))
    print(f"anonymous instances (reachable only through instance search): {anonymous}")
    print(f"full names declared more than once: {g.repeated}")
    start = [v for v in range(len(g)) if imports.module_of(g.paths[g.files[v]], src_dir) in roots]
    t = declgraph.dominator_tree(g, start)
    reached = list(t.idom)
    total_lines = sum(g.sizes)
    hit_lines = sum(g.sizes[v] for v in reached)
    print(f"\nroots: {len(start)} declarations in {', '.join(sorted(roots))}")
    print(
        f"reached by name from the roots: {len(reached)} declarations "
        f"({100 * len(reached) / max(len(g), 1):.1f}%), {hit_lines} of {total_lines} lines"
    )
    every = declgraph.folders(g, range(len(g)), args.folder_depth)
    hit = declgraph.folders(g, reached, args.folder_depth)
    rows = [(k, n, hit[k], f"{100 * hit[k] / n:.0f}%") for k, n in every.most_common(args.top) if n]
    print(table(rows, ["folder", "lines", "reached", "share"]))
    floor = max(1, round(args.min_share * hit_lines))
    tree = declgraph.spine(t, floor, args.depth)
    print(f"\ndominator tree, subtrees of at least {floor} lines, depth {args.depth}:")
    out_rows = []
    for depth, v in tree:
        print(f"{'  ' * depth}{g.names[v]}  [{t.count[v]} decls, {t.lines[v]} lines]  {g.where(v)}")
        out_rows.append((depth, g.names[v], t.lines[v], f"({t.count[v]:,} decls)"))
    if args.svg:
        args.svg.parent.mkdir(parents=True, exist_ok=True)
        title = f"Dominator tree from {', '.join(sorted(roots))} ({len(reached):,} declarations)"
        args.svg.write_text(declgraph.svg(out_rows, title), encoding="utf-8")
        print(f"wrote {args.svg}")
    dump(
        args.json,
        {
            "declarations": len(g),
            "kinds": dict(kinds),
            "references": edges,
            "anonymous_instances": anonymous,
            "repeated_names": g.repeated,
            "roots": [g.names[v] for v in start],
            "reached": len(reached),
            "reached_lines": hit_lines,
            "lines": total_lines,
            "folders": {k: [n, hit[k]] for k, n in every.items()},
            "tree": [
                {
                    "depth": depth,
                    "name": g.names[v],
                    "at": g.where(v),
                    "decls": t.count[v],
                    "lines": t.lines[v],
                }
                for depth, v in tree
            ],
        },
    )
    return 0


def cmd_imports(args) -> int:
    lk = lake.load(args.root)
    src_dir = lk.config.get("srcDir", ".")
    g = imports.build_pairs(sources(args), src_dir)
    roots = args.roots or lake.roots(lk)
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


def cmd_forms(args) -> int:
    rows = [(f.name, f.relation, f.source, f.file) for f in forms.FORMS]
    print(table(rows, ["form", "relation", "source", "file"]))
    return 0


def cmd_criteria(args) -> int:
    exc = criteria.robin_exceptions(args.robin)
    largest = f", largest {exc[-1]}" if exc else ""
    print(f"Robin, n <= {args.robin}: {len(exc)} exceptions{largest}")
    print("  " + " ".join(map(str, exc)))
    lag = criteria.lagarias(args.robin)
    print(
        f"Lagarias, n <= {args.robin}: {len(lag.violations)} violations, equality at "
        f"{lag.equal}, tightest n = {lag.tightest} (relative slack {lag.slack:.4g})"
    )
    lam = li.li_coefficients(args.li, r=args.radius, m=args.points)
    rows = [(n, f"{x:.12f}") for n, x in enumerate(lam, 1)]
    print(f"\nLi coefficients (contour r = {args.radius}, {args.points} points)")
    print(table(rows, ["n", "lambda_n"]))
    if args.baez_duarte:
        d = criteria.baez_duarte(args.baez_duarte)
        rows = [(n, f"{x:.9f}", f"{x * math.log(n):.6f}") for n, x in enumerate(d, 1)]
        print("\nBaez-Duarte distance")
        print(table(rows, ["N", "d_N^2", "d_N^2 log N"]))
    return 0


def cmd_li(args) -> int:
    lam = li.li_coefficients(args.n, r=args.radius, m=args.points)
    gammas = zeros.ordinates(args.zeros + 1)
    sums = [li.from_zeros(n, gammas) for n in range(1, args.n + 1)]
    boxes = []
    if args.certify:
        boxes = enclose.li_enclosures(args.n, str(args.radius), args.points, args.dps)
    rows, body = [], []
    for n, x in enumerate(lam, 1):
        z = sums[n - 1]
        arch = li.archimedean(n)
        row = [n, f"{x:.12f}", f"{z.estimate - x:+.1e}", f"{z.partial:.6f}"]
        row += [f"{z.partial + z.upper:.6f}", f"{arch:.9f}", f"{x - arch:.9f}"]
        entry = {"n": n, "contour": x, "zeros": asdict(z), "archimedean": arch}
        if boxes:
            e = boxes[n - 1]
            row += [e.decimals(15)[0], mpmath.nstr(e.width, 2)]
            entry["certified"] = list(e.decimals(args.dps))
        rows.append(row)
        body.append(entry)
    head = ["n", "contour", "zeros-contour", "sum lo", "sum hi", "archimedean", "finite"]
    print(f"Li coefficients: {args.zeros} zeros, height {sums[0].height:.2f}")
    print(table(rows, head + (["certified lo", "width"] if boxes else [])))
    if boxes:
        positive = all(e.lo > 0 for e in boxes)
        print(f"\nlambda_1..lambda_{args.n} certified positive: {positive}")
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
    s.add_argument("--manifest", type=Path, default=Path("manifest.json"))
    s.add_argument("--record", action="store_true", help="store the joined hash if missing")
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

    s = sub.add_parser("manuscript", help="numbered results, cross-references and markers")
    s.add_argument("text", type=Path, help="page-numbered text from pdftext")
    s.add_argument("--index", action="store_true", help="print every numbered result")
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--json", type=Path)
    s.set_defaults(run=cmd_manuscript)

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

    s = sub.add_parser("audit", help="every static check on a Lean project, one JSON report")
    s.add_argument("root", type=Path)
    s.add_argument("--module", action="append", help="statement modules (default: lib roots)")
    s.add_argument("--severity", choices=audit.SEVERITIES, default="medium")
    s.add_argument("--json", type=Path)
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_audit)

    s = sub.add_parser("imports", help="import graph and the cone of the statement modules")
    s.add_argument("root", type=Path)
    s.add_argument("--roots", nargs="+")
    s.add_argument("--hatches", type=Path, help="scan JSON to split by cone")
    s.add_argument("--json", type=Path)
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_imports)

    s = sub.add_parser("decls", help="declaration graph from source and its dominator tree")
    s.add_argument("root", type=Path)
    s.add_argument("--roots", nargs="+", help="modules whose declarations start the walk")
    s.add_argument("--min-share", type=float, default=0.01)
    s.add_argument("--depth", type=int, default=8)
    s.add_argument("--folder-depth", type=int, default=3)
    s.add_argument("--top", type=int, default=25)
    s.add_argument("--json", type=Path)
    s.add_argument("--svg", type=Path)
    s.add_argument("--archive", type=Path, help="read .lean files from STEM.partNN")
    s.add_argument("--under", default="", help="archive folder that holds the project")
    s.set_defaults(run=cmd_decls)

    s = sub.add_parser("forms", help="the statement library: RH and its equivalent forms")
    s.set_defaults(run=cmd_forms)

    s = sub.add_parser("criteria", help="numerical checks of Robin, Lagarias, Li and Baez-Duarte")
    s.add_argument("--robin", type=int, default=100_000, help="check n up to this")
    s.add_argument("--li", type=int, default=20, help="Li coefficients up to this n")
    s.add_argument("--radius", type=float, default=0.8)
    s.add_argument("--points", type=int, default=512)
    s.add_argument("--baez-duarte", type=int, default=0, metavar="N", help="d_N^2 up to N")
    s.set_defaults(run=cmd_criteria)

    s = sub.add_parser("li", help="Li coefficients from the contour, the zeros and intervals")
    s.add_argument("--n", type=int, default=20)
    s.add_argument("--zeros", type=int, default=100, help="zeros summed before the tail")
    s.add_argument("--radius", type=float, default=0.8)
    s.add_argument("--points", type=int, default=512)
    s.add_argument("--certify", action="store_true", help="interval enclosures")
    s.add_argument("--dps", type=int, default=30)
    s.add_argument("--json", type=Path)
    s.set_defaults(run=cmd_li)

    args = p.parse_args(argv)
    return args.run(args)
