from zeta_checker import imports


def test_graph_of_fixture_project(fixtures):
    g = imports.build(fixtures / "project/src")
    assert g.imports["Main"] == ["Statements", "Proof.Core"]
    assert g.cone(["Statements", "Main"]) == {"Main", "Statements", "Proof.Core"}
    assert g.external() == {"Mathlib": 3}
    assert g.totals(["Statements"])[0] == 1
    assert g.unresolved({"Mathlib"}) == []
    want = [(m, "Mathlib") for m in ("Proof.Core", "Proof.Shadow", "Statements")]
    assert sorted(g.unresolved(set())) == want


def test_header_imports_only():
    src = (
        "/- Copyright (c) 2026 X. Released under Apache 2.0 license -/\n"
        "import A.B\n-- import C\nimport all D\npublic import E\n/- import F -/\n"
    )
    assert imports._IMPORT.findall(imports.mask(src).text) == ["A.B", "D", "E"]


def test_shadowing_and_headers(tmp_path):
    (tmp_path / "Mathlib").mkdir()
    (tmp_path / "Mathlib/Fake.lean").write_text("/- Copyright (c) 2026 -/\ndef x := 1\n")
    (tmp_path / "Own.lean").write_text("import Mathlib.Fake\nimport Nowhere.Thing\n")
    g = imports.build(tmp_path)
    assert g.shadowing({"Mathlib"}) == ["Mathlib.Fake"]
    assert g.headers == ["Mathlib.Fake"]
    assert g.unresolved({"Mathlib"}) == [("Own", "Nowhere.Thing")]


def test_module_of():
    assert imports.module_of("src/A/B.lean", "src") == "A.B"
    assert imports.module_of("Top.lean") == "Top"
