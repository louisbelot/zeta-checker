from zeta_checker import hatches, statements
from zeta_checker.reference import MATHLIB_RH

SRC = """import Mathlib

namespace A

/-- doc mentioning theorem fake : False -/
theorem foo (x : ℕ) (h : 0 < x) :
    x ≠ 0 := by
  omega

namespace B.C

def bar : Prop :=
  ∀ s : ℂ, s = s

end B.C

theorem _root_.baz : True := trivial

instance : Inhabited ℕ := ⟨0⟩

end A

-- theorem commented : False := sorry
theorem top : True := trivial
"""


def test_parse_names_and_signatures():
    mod = statements.parse(SRC, "X.lean")
    assert mod.imports == ["Mathlib"]
    got = [(d.kind, d.full, d.line) for d in mod.decls]
    assert got == [
        ("theorem", "A.foo", 6),
        ("def", "A.B.C.bar", 12),
        ("theorem", "baz", 17),
        ("instance", "", 19),
        ("theorem", "top", 24),
    ]
    foo, bar = mod.decls[0], mod.decls[1]
    assert foo.signature == "theorem foo (x : ℕ) (h : 0 < x) : x ≠ 0"
    assert foo.body == "by omega"
    assert bar.body == "∀ s : ℂ, s = s"
    assert statements.split_signature(foo.signature, foo.name) == (
        "(x : ℕ) (h : 0 < x)",
        "x ≠ 0",
    )
    assert statements.statement(foo) == "∀ (x : ℕ) (h : 0 < x), x ≠ 0"


def test_shape_of_mathlib_rh():
    assert statements.shape(MATHLIB_RH.statement) == [
        ("binder", "s : ℂ"),
        ("premise", "riemannZeta s = 0"),
        ("premise", "¬∃ n : ℕ, s = -2 * (n + 1)"),
        ("premise", "s ≠ 1"),
        ("conclusion", "s.re = 1 / 2"),
    ]


ARROWS = "∀ s : ℂ, riemannZeta s = 0 → (¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)) → s ≠ 1 → s.re = 1 / 2"


def test_compare_arrow_form_with_mathlib():
    rows = statements.compare(ARROWS, MATHLIB_RH.statement)
    assert [r[3] for r in rows[:2]] + [r[3] for r in rows[3:]] == ["same"] * 4
    assert rows[2][0] == "premise"
    assert rows[2][3] == "only here: `(`; only here: `: ℂ )`"


def test_compare_reports_missing_premise():
    weaker = "∀ (s : ℂ) (_ : riemannZeta s = 0) (_ : s ≠ 1), s.re = 1 / 2"
    rows = statements.compare(weaker, MATHLIB_RH.statement)
    assert [r[3] for r in rows] == ["same", "same", "only in reference", "same", "same"]
    assert rows[2][2] == "¬∃ n : ℕ, s = -2 * (n + 1)"


def test_nested_forall_and_unparenthesized_exists():
    grh = (
        "∀ (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive → "
        "∀ s : ℂ, 0 < s.re → s.re < 1 → DirichletCharacter.LFunction χ s = 0 → s.re = 1 / 2"
    )
    assert [k for k, _ in statements.shape(grh)] == [
        "binder",
        "binder",
        "binder",
        "premise",
        "binder",
        "premise",
        "premise",
        "premise",
        "conclusion",
    ]
    assert statements.shape("∀ s, ¬∃ n, s = n → False") == [
        ("binder", "s"),
        ("conclusion", "¬∃ n, s = n → False"),
    ]


def test_names_skip_bound_variables():
    items = statements.shape(MATHLIB_RH.statement)
    got = statements.names(MATHLIB_RH.statement, statements.bound_names(items))
    assert got == ["ℂ", "riemannZeta", "ℕ", ".re"]


def test_trace_finds_shadowing(fixtures):
    root = fixtures / "project"
    files = hatches.relative(root)
    declared, overrides = statements.trace(files, {"riemannZeta", "RiemannHypothesis"})
    assert declared == [("src/Proof/Shadow.lean", 5, "def", "riemannZeta")]
    assert overrides == [
        ("src/Proof/Shadow.lean", 9, "notation", '"RiemannHypothesis"'),
    ]
