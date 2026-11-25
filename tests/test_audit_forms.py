from pathlib import Path

from zeta_checker import audit, forms, hatches

CHALLENGES = Path(__file__).parent.parent / "challenges"
HEAD = "import Mathlib\n\n"
LAKEFILE = """name = "fake"
defaultTargets = ["Main"]

[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4"
rev = "v4.33.1"

[[lean_lib]]
name = "Main"
"""


def test_audit_reads_the_challenges():
    modules = sorted(f"Challenges.{p.stem}" for p in (CHALLENGES / "Challenges").glob("*.lean"))
    report = audit.run(CHALLENGES, lambda: hatches.read(CHALLENGES), modules)
    refs = {t["decl"]: (t["reference"], t["exact"]) for t in report["theorems"]}
    assert refs["riemann_hypothesis"] == ("RiemannHypothesis", True)
    assert refs["robin"] == ("ZetaForms.Robin", True)
    assert all(exact for _, exact in refs.values()) and len(refs) == len(forms.FORMS) + 1
    codes = [(f["severity"], f["code"]) for f in report["findings"]]
    assert codes.count(("critical", "hatch sorry")) == len(refs)
    assert codes.count(("info", "equivalent-form")) == len(forms.FORMS)
    assert ("medium", "statement-differs") not in codes


def fake(root, main):
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.33.1\n", encoding="utf-8")
    (root / "lakefile.toml").write_text(LAKEFILE, encoding="utf-8")
    (root / "Main.lean").write_text(HEAD + main, encoding="utf-8")
    report = audit.run(root, lambda: hatches.read(root))
    return report["theorems"][0], report["findings"]


def test_inline_robin_is_recognised(tmp_path):
    t, found = fake(
        tmp_path, f"theorem robin : {forms.BY_NAME['ZetaForms.Robin'].statement} := by\n  simp\n"
    )
    assert (t["reference"], t["exact"]) == ("ZetaForms.Robin", True)
    assert any(f["code"] == "equivalent-form" for f in found)


def test_moved_robin_threshold_differs(tmp_path):
    stmt = forms.BY_NAME["ZetaForms.Robin"].statement.replace("5040", "2520")
    t, found = fake(tmp_path, f"theorem robin : {stmt} := by\n  simp\n")
    assert (t["reference"], t["exact"]) == ("ZetaForms.Robin", False)
    diffs = [f["detail"] for f in found if f["code"] == "statement-differs"]
    assert len(diffs) == 1 and "`2520` here, `5040` in reference" in diffs[0]


def test_li_through_project_definitions(tmp_path):
    main = (
        "noncomputable def lam (n : ℕ) : ℝ :=\n"
        "  (iteratedDeriv n (fun s : ℂ => s ^ (n - 1) * Complex.log (xi s)) 1).re\n\n"
        "def LiCriterion : Prop := ∀ n : ℕ, 1 ≤ n → 0 ≤ lam n\n\n"
        "theorem li : LiCriterion := by\n  simp\n"
    )
    t, found = fake(tmp_path, main)
    assert (t["reference"], t["exact"]) == ("ZetaForms.Li", False)
    assert any("`lam` here, `liCoeff` in reference" in f["detail"] for f in found)
