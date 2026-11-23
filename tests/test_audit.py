import json

import pytest

from zeta_checker import audit, hatches
from zeta_checker.cli import main

MATHLIB = "0df444a360eaa60ab8c11dca51a86af692955474"
LAKEFILE = f"""name = "fake"
srcDir = "src"
defaultTargets = ["Main"]
{{options}}
[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4"
rev = "{MATHLIB}"

[[lean_lib]]
name = "Main"
roots = ["Main"]
"""
MANIFEST = {
    "version": "1.1.0",
    "packagesDir": ".lake/packages",
    "packages": [
        {
            "name": "mathlib",
            "url": "https://github.com/leanprover-community/mathlib4",
            "rev": MATHLIB,
            "inputRev": MATHLIB,
            "inherited": False,
            "type": "git",
            "scope": "",
        }
    ],
}
HEAD = "import Mathlib\n\n"
MAIN = "import Mathlib\nimport Proof\n\ntheorem riemannHypothesis : RiemannHypothesis := Proof.rh\n"
PROOF = HEAD + "namespace Proof\n\ntheorem rh : RiemannHypothesis := by\n  simp\n\nend Proof\n"
RESTATED = (
    HEAD + "theorem zeros : ∀ (s : ℂ) (_ : riemannZeta s = 0) "
    "(_ : ¬∃ n : ℕ, s = -2 * (n + 1)) (_ : s ≠ 1), s.re = {re} := by\n  simp\n"
)


def project(root, files=None, options="", toolchain="leanprover/lean4:v4.33.1", rev=MATHLIB):
    files = {"src/Main.lean": MAIN, "src/Proof.lean": PROOF} | (files or {})
    (root / "lean-toolchain").write_text(toolchain + "\n", encoding="utf-8")
    (root / "lakefile.toml").write_text(LAKEFILE.format(options=options), encoding="utf-8")
    manifest = MANIFEST | {"packages": [MANIFEST["packages"][0] | {"rev": rev}]}
    (root / "lake-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for rel, text in files.items():
        if text is None:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return audit.run(root, lambda: hatches.read(root))


def flagged(report, floor="medium"):
    keep = audit.SEVERITIES[: audit.SEVERITIES.index(floor) + 1]
    return {(f["severity"], f["code"]) for f in report["findings"] if f["severity"] in keep}


def test_clean_project_has_nothing_to_flag(tmp_path):
    report = project(tmp_path)
    assert flagged(report) == set()
    assert report["theorems"][0]["exact"] and audit.worst(report) is None
    assert report["cone"] == {"modules": 2, "lines": 12}


PLANTED = {
    "vacuous hypothesis": (
        {"src/Main.lean": HEAD + "theorem rh (h : False) : RiemannHypothesis := h.elim\n"},
        "",
        ("critical", "vacuous-hypothesis"),
    ),
    "negated truth": (
        {"src/Main.lean": HEAD + "theorem rh : ¬ True → RiemannHypothesis := by\n  simp\n"},
        "",
        ("critical", "vacuous-hypothesis"),
    ),
    "circular hypothesis": (
        {"src/Main.lean": HEAD + "theorem rh (h : RiemannHypothesis) : RiemannHypothesis := h\n"},
        "",
        ("critical", "circular-hypothesis"),
    ),
    "hypothesis from the project": (
        {
            "src/Main.lean": (
                "import Mathlib\nimport Proof\n\n"
                "theorem rh (h : Proof.Assumption) : RiemannHypothesis := Proof.rh\n"
            ),
            "src/Proof.lean": PROOF.replace(
                "namespace Proof\n", "namespace Proof\n\ndef Assumption : Prop := False\n"
            ),
        },
        "",
        ("high", "hypothesis-project-name"),
    ),
    "extra axiom": (
        {"src/Proof.lean": HEAD + "namespace Proof\n\naxiom rh : RiemannHypothesis\n\nend Proof\n"},
        "",
        ("critical", "hatch axiom"),
    ),
    "kernel bypass in source": (
        {
            "src/Proof.lean": PROOF.replace(
                "theorem rh", "set_option debug.skipKernelTC true in\ntheorem rh"
            )
        },
        "",
        ("critical", "hatch set_option debug.skipKernelTC"),
    ),
    "kernel bypass in the lakefile": (
        {},
        "[leanOptions]\ndebug.skipKernelTC = true\n",
        ("critical", "lake-option debug.skipKernelTC"),
    ),
    "kernel bypass as a lean argument": (
        {},
        'moreLeanArgs = ["-Ddebug.skipKernelTC=true"]\n',
        ("critical", "lake-option debug.skipKernelTC"),
    ),
    "sorry behind a macro": (
        {
            "src/Proof.lean": (
                'import Mathlib\n\nmacro "done" : tactic => `(tactic| sorry)\n\n'
                "namespace Proof\n\ntheorem rh : RiemannHypothesis := by\n  done\n\nend Proof\n"
            )
        },
        "",
        ("critical", "hatch sorry"),
    ),
    "native_decide": (
        {"src/Proof.lean": PROOF.replace("  simp\n", "  native_decide\n")},
        "",
        ("high", "hatch native_decide"),
    ),
    "goal assigned without a type check": (
        {
            "src/Proof.lean": (
                "import Lean\nimport Mathlib\n\nopen Lean Elab Tactic in\n"
                'elab "trust " t:term : tactic => do\n'
                "  (← getMainGoal).assign (← Term.elabTerm t none)\n\n"
                "namespace Proof\n\ntheorem rh : RiemannHypothesis := by\n  trust 0\n\nend Proof\n"
            )
        },
        "",
        ("medium", "hatch MVarId.assign"),
    ),
    "shadowed zeta": (
        {
            "src/Main.lean": RESTATED.format(re="1 / 2").replace(
                "import Mathlib\n", "import Mathlib\nimport Proof\n"
            ),
            "src/Proof.lean": "import Mathlib\n\ndef riemannZeta (s : ℂ) : ℂ := 1\n",
        },
        "",
        ("high", "declares-statement-name"),
    ),
    "notation over the statement": (
        {"src/Proof.lean": PROOF + '\nnotation "RiemannHypothesis" => True\n'},
        "",
        ("high", "notation-on-statement-name"),
    ),
    "wrong line": (
        {"src/Main.lean": RESTATED.format(re="1 / 3")},
        "",
        ("medium", "statement-differs"),
    ),
    "no RH at all": (
        {"src/Main.lean": "import Mathlib\n\ntheorem easy : (1 : ℕ) + 1 = 2 := rfl\n"},
        "",
        ("high", "no-rh-statement"),
    ),
    "lakefile.lean": (
        {"lakefile.lean": "import Lake\nopen Lake DSL\n\npackage fake\n"},
        "",
        ("high", "lakefile-lean"),
    ),
    "module named like Mathlib": (
        {"src/Mathlib/NumberTheory/LSeries/RiemannZeta.lean": "def RiemannHypothesis := True\n"},
        "",
        ("high", "module-shadows-dependency"),
    ),
}


@pytest.mark.parametrize("case", PLANTED)
def test_planted_failure_is_flagged(tmp_path, case):
    files, options, want = PLANTED[case]
    assert want in flagged(project(tmp_path, files, options))


def test_hatches_outside_the_cone_are_low(tmp_path):
    report = project(tmp_path, {"src/Stray.lean": "axiom magic : False\n"})
    rows = [(f["severity"], f["code"], f["file"]) for f in report["findings"]]
    assert rows == [("low", "hatch axiom", "src/Stray.lean")]


def test_manifest_must_match_the_pin(tmp_path):
    assert ("medium", "pin-mismatch") in flagged(project(tmp_path, rev="f" * 40))


def test_toolchain_must_be_a_release(tmp_path):
    report = project(tmp_path, toolchain="someone/lean4:patched")
    assert ("high", "toolchain") in flagged(report)


def test_harmless_lake_options(tmp_path):
    report = project(tmp_path, options="[leanOptions]\nautoImplicit = false\nmaxHeartbeats = 0\n")
    assert flagged(report) == set()


def test_audit_command_exit_codes(tmp_path, capsys):
    clean, bad = tmp_path / "clean", tmp_path / "bad"
    clean.mkdir()
    bad.mkdir()
    project(clean)
    project(bad, {"src/Proof.lean": PROOF.replace("simp", "sorry")})
    out = tmp_path / "audit.json"
    assert main(["audit", str(clean)]) == 0
    assert main(["audit", str(bad), "--json", str(out)]) == 2
    text = capsys.readouterr().out
    assert "[critical] hatch sorry  src/Proof.lean:6" in text
    body = json.loads(out.read_text(encoding="utf-8"))
    assert body["schema"] == audit.SCHEMA and body["severity"]["critical"] == 1


def test_report_is_stable(tmp_path):
    a = project(tmp_path, {"src/Stray.lean": "axiom a : False\naxiom b : False\n"})
    b = audit.run(tmp_path, lambda: reversed(list(hatches.read(tmp_path))))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
