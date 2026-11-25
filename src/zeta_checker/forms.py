from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from zeta_checker import statements


@dataclass(frozen=True)
class Form:
    name: str
    file: str
    relation: str
    source: str
    keys: frozenset[str]
    statement: str


def _form(name, file, relation, source, keys, statement):
    return Form(f"ZetaForms.{name}", file, relation, source, frozenset(keys), statement)


FORMS = (
    _form(
        "HalfPlane",
        "ZetaForms/RH.lean",
        "equivalent to RH",
        "functional equation",
        (),
        "∀ s : ℂ, 1 / 2 < s.re → riemannZeta s ≠ 0",
    ),
    _form(
        "GRH",
        "ZetaForms/GRH.lean",
        "implies RH",
        "standard",
        ("LFunction",),
        "∀ {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ), "
        "χ.LFunction s = 0 → 0 < s.re → s.re < 1 → s.re = 1 / 2",
    ),
    _form(
        "GRHPrimitive",
        "ZetaForms/GRH.lean",
        "implies RH",
        "standard",
        ("LFunction", "IsPrimitive"),
        "∀ {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive → ∀ s : ℂ, "
        "χ.LFunction s = 0 → 0 < s.re → s.re < 1 → s.re = 1 / 2",
    ),
    _form(
        "Robin",
        "ZetaForms/Divisors.lean",
        "equivalent to RH",
        "Robin 1984",
        ("sigma", "eulerMascheroniConstant"),
        "∀ n : ℕ, 5040 < n → (ArithmeticFunction.sigma 1 n : ℝ) < "
        "Real.exp Real.eulerMascheroniConstant * n * Real.log (Real.log n)",
    ),
    _form(
        "Lagarias",
        "ZetaForms/Divisors.lean",
        "equivalent to RH",
        "Lagarias 2002",
        ("sigma", "harmonic"),
        "∀ n : ℕ, 1 ≤ n → (ArithmeticFunction.sigma 1 n : ℝ) ≤ "
        "(harmonic n : ℝ) + Real.exp (harmonic n : ℝ) * Real.log (harmonic n : ℝ)",
    ),
    _form(
        "Mertens",
        "ZetaForms/Mertens.lean",
        "equivalent to RH",
        "Littlewood 1912",
        ("moebius",),
        "∀ ε : ℝ, 0 < ε → ∃ C : ℝ, ∀ x : ℕ, "
        "|∑ n ∈ Finset.Icc 1 x, (ArithmeticFunction.moebius n : ℝ)| ≤ "
        "C * (x : ℝ) ^ ((1 : ℝ) / 2 + ε)",
    ),
    _form(
        "Li",
        "ZetaForms/Li.lean",
        "equivalent to RH",
        "Li 1997",
        ("iteratedDeriv",),
        "∀ n : ℕ, 1 ≤ n → 0 ≤ liCoeff n",
    ),
    _form(
        "BaezDuarte",
        "ZetaForms/BaezDuarte.lean",
        "equivalent to RH",
        "Báez-Duarte 2003",
        ("fract",),
        "∀ ε : ℝ, 0 < ε → ∃ (N : ℕ) (c : ℕ → ℝ), ∫⁻ t in Set.Ioi (0 : ℝ), "
        "ENNReal.ofReal ((Set.indicator (Set.Ioc (0 : ℝ) 1) (fun _ => (1 : ℝ)) t - "
        "∑ k ∈ Finset.range N, c k * Int.fract (1 / ((k + 1 : ℝ) * t))) ^ 2) < ENNReal.ofReal ε",
    ),
)

BY_NAME = {f.name: f for f in FORMS}


def lookup(stmt: str, expr: str, found: Iterable[str]) -> tuple[Form | None, bool]:
    if stmt in BY_NAME:
        return BY_NAME[stmt], True
    toks = statements.tokens(statements.squash(expr))
    for f in FORMS:
        if toks == statements.tokens(statements.squash(f.statement)):
            return f, True
    have = {n.rsplit(".", 1)[-1] for n in found}
    hits = [f for f in FORMS if f.keys and f.keys <= have]
    return (max(hits, key=lambda f: len(f.keys)), False) if hits else (None, False)
