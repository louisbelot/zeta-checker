import Mathlib

namespace ZetaForms

def Mertens : Prop :=
  ∀ ε : ℝ, 0 < ε → ∃ C : ℝ, ∀ x : ℕ,
    |∑ n ∈ Finset.Icc 1 x, (ArithmeticFunction.moebius n : ℝ)| ≤ C * (x : ℝ) ^ ((1 : ℝ) / 2 + ε)

end ZetaForms
