from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    name: str
    repo: str
    rev: str
    path: str
    line: int
    statement: str


MATHLIB_RH = Reference(
    name="RiemannHypothesis",
    repo="leanprover-community/mathlib4",
    rev="0df444a360eaa60ab8c11dca51a86af692955474",
    path="Mathlib/NumberTheory/LSeries/RiemannZeta.lean",
    line=185,
    statement=(
        "∀ (s : ℂ) (_ : riemannZeta s = 0) (_ : ¬∃ n : ℕ, s = -2 * (n + 1)) (_ : s ≠ 1), "
        "s.re = 1 / 2"
    ),
)

REFERENCES = {MATHLIB_RH.name: MATHLIB_RH}
