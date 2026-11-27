import random
import re

import pytest

from zeta_checker import statements
from zeta_checker.forms import FORMS
from zeta_checker.reference import MATHLIB_RH

alpha = statements.alpha_equal


def test_renamed_rh_is_mathlib():
    renamed = (
        "∀ (z : ℂ) (_ : riemannZeta z = 0) (_ : ¬∃ k : ℕ, z = -2 * (k + 1)) (_ : z ≠ 1), "
        "z.re = 1 / 2"
    )
    assert alpha(renamed, MATHLIB_RH.statement)


def test_named_hypotheses_are_premises():
    named = (
        "∀ (s : ℂ) (hz : riemannZeta s = 0) (htriv : ¬∃ n : ℕ, s = -2 * (n + 1)) "
        "(h1 : s ≠ 1), s.re = 1 / 2"
    )
    assert alpha(named, MATHLIB_RH.statement)


def test_used_hypothesis_stays_a_binder():
    a = "∀ (n : ℕ) (h : 0 < n), f n h = 0"
    b = "∀ (n : ℕ), 0 < n → f n h = 0"
    assert not alpha(a, b)


def test_binder_grouping():
    assert alpha("∀ (a b : ℕ), a + b = b + a", "∀ (x : ℕ) (y : ℕ), x + y = y + x")
    assert alpha("∀ a b : ℕ, a ≤ b", "∀ (a : ℕ), ∀ (b : ℕ), a ≤ b")


def test_swapped_variables_differ():
    assert not alpha("∀ (a b : ℕ), a - b = 0", "∀ (a b : ℕ), b - a = 0")
    assert alpha("∀ (a b : ℕ), a - b = 0", "∀ (b a : ℕ), b - a = 0")


def test_inner_binders():
    assert alpha("∀ s : ℂ, ∃ n : ℕ, s = n", "∀ t : ℂ, ∃ m : ℕ, t = m")
    assert alpha("∀ x, (fun y => y + x) 1 = 2", "∀ a, (fun b ↦ b + a) 1 = 2")
    assert alpha("∀ ε > 0, ∃ δ > 0, δ < ε", "∀ e > 0, ∃ d > 0, d < e")
    assert alpha("∀ n, ∑ i ∈ Finset.range n, i = 0", "∀ m, ∑ k ∈ Finset.range m, k = 0")
    assert alpha("∀ n, {x : ℕ | x < n}.Finite", "∀ m, {y : ℕ | y < m}.Finite")


def test_inner_scope_ends_at_bracket():
    a = "∀ n : ℕ, (∃ m : ℕ, m = n) ∧ m = 0"
    b = "∀ n : ℕ, (∃ k : ℕ, k = n) ∧ m = 0"
    c = "∀ n : ℕ, (∃ k : ℕ, k = n) ∧ k = 0"
    assert alpha(a, b)
    assert not alpha(a, c)


def test_no_capture_of_free_names():
    assert not alpha("∀ x : ℕ, x = y", "∀ y : ℕ, y = y")
    assert not alpha("∀ x : ℕ, ∃ y : ℕ, x = y", "∀ x : ℕ, ∃ x : ℕ, x = x")


def test_type_annotations_inside_groups_are_not_names():
    assert alpha(
        "∀ (χ : DirichletCharacter ℂ N), ∃ (s : Set (ℂ)), χ ∈ s",
        "∀ (ψ : DirichletCharacter ℂ N), ∃ (t : Set (ℂ)), ψ ∈ t",
    )


def test_rename_reports_inner_names():
    out, inner = statements.rename("∃ a b : ℕ, a < b ∧ c", {"c": "C"}, lambda i, n: f"v{i}")
    assert inner == ["a", "b"]
    assert out == "∃ v0 v1 : ℕ, v0 < v1 ∧ C"


def test_renamed_row_shows_real_difference():
    rows = statements.compare(
        "∀ (z : ℂ), riemannZeta z = 0 → z.re = 1 / 3", "∀ (s : ℂ), riemannZeta s = 0 → s.re = 1 / 2"
    )
    assert [r[3] for r in rows] == ["same", "same", "`3` here, `2` in reference"]


def _bound(stmt: str) -> list[str]:
    items = statements.shape(stmt)
    names = statements.bound_names(items)
    return sorted(n for n in names if n != "_")


def _rename_all(stmt: str, rng: random.Random) -> str:
    pool = [f"v{rng.randrange(10**6)}" for _ in range(40)]
    mapping = dict(zip(_bound(stmt), pool, strict=False))
    pattern = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, mapping)) + r")(?![\w'])")
    return pattern.sub(lambda m: mapping[m.group()], stmt)


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.name)
def test_random_renaming_of_forms(form):
    rng = random.Random(form.name)
    for _ in range(20):
        renamed = _rename_all(form.statement, rng)
        assert alpha(renamed, form.statement), renamed


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.name)
def test_forms_differ_from_each_other(form):
    for other in FORMS:
        if other is not form:
            assert not alpha(form.statement, other.statement)


def test_binder_predicate_is_a_premise():
    assert alpha("∀ ε > 0, ε ≠ 0", "∀ e, e > 0 → e ≠ 0")
    assert alpha("∀ x ∈ S, f x = 0", "∀ (y : α), y ∈ S → f y = 0") is False
    assert alpha("∀ x ∈ S, f x = 0", "∀ y, y ∈ S → f y = 0")


def test_spelling_variants():
    assert alpha("∀ x : ℕ, x = x -> True", "∀ y : ℕ, y = y → True")
    assert alpha("∀ x, (λ y => y) x = x", "∀ x, (fun z ↦ z) x = x")
