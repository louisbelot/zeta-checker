import re
from collections import Counter

from zeta_checker import hatches

MARK = re.compile(r"--\s*expect:\s*(.+)$")


def expected(path) -> Counter:
    out = Counter()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = MARK.search(line)
        if m:
            out.update((n, rule.strip()) for rule in m.group(1).split(","))
    return out


def found(path) -> Counter:
    src = path.read_text(encoding="utf-8")
    return Counter((h.line, h.rule) for h in hatches.scan_source(src, path.name))


def test_every_planted_hatch_is_found(fixtures):
    path = fixtures / "lean/planted.lean"
    want, got = expected(path), found(path)
    assert got - want == Counter(), "unexpected hits"
    assert want - got == Counter(), "missed hits"


def test_decoys_do_not_count(fixtures):
    path = fixtures / "lean/decoys.lean"
    assert found(path) == expected(path)


def test_risk_and_names():
    src = (
        "axiom bad : False\n"
        "set_option debug.skipKernelTC true\n"
        "set_option maxRecDepth 2000\n"
        "opaque hidden : Nat\n"
        "theorem t : False := sorry\n"
    )
    hits = {h.rule: h for h in hatches.scan_source(src, "x.lean")}
    assert hits["axiom"].name == "bad" and hits["axiom"].risk == "critical"
    assert hits["set_option debug.skipKernelTC"].group == "kernel"
    assert hits["set_option debug.skipKernelTC"].risk == "critical"
    assert hits["set_option maxRecDepth"].risk == "low"
    assert hits["opaque"].name == "hidden"
    assert hits["sorry"].text == "theorem t : False := sorry"


def test_attribute_context():
    src = "@[simp, implemented_by fast]\ndef slow := 1\ndef implemented_by := 2\n"
    rules = [(h.line, h.rule) for h in hatches.scan_source(src, "x.lean")]
    assert rules == [(1, "implemented_by")]
    src = 'attribute [extern "c_f"] f\nattribute [local instance] g\n'
    assert [h.rule for h in hatches.scan_source(src, "x.lean")] == ["extern"]


def test_scan_tree_and_counts(fixtures):
    report = hatches.scan(fixtures / "lean")
    assert report.files == 2 and not report.bad_utf8
    counts = {row[2]: row for row in report.counts()}
    assert counts["sorry"][3:] == (10, 1)
    assert report.counts()[0][0] == "critical"
    body = report.as_dict()
    assert body["counts"] and body["hits"][0]["file"] in ("decoys.lean", "planted.lean")


def test_invalid_utf8_is_reported(tmp_path):
    (tmp_path / "bad.lean").write_bytes(b"theorem t : False := sorry \xff\n")
    report = hatches.scan(tmp_path)
    assert report.bad_utf8 == ["bad.lean"]
    assert [h.rule for h in report.hits] == ["sorry"]


def test_lake_and_git_dirs_are_skipped(tmp_path):
    for sub in (".lake/packages/x", ".git", "src"):
        (tmp_path / sub).mkdir(parents=True)
        (tmp_path / sub / "f.lean").write_text("theorem t : False := sorry\n")
    assert [p.parent.name for p in hatches.lean_files(tmp_path)] == ["src"]
