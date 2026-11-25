import Mathlib

namespace ZetaForms

def Robin : Prop :=
  ∀ n : ℕ, 5040 < n →
    (ArithmeticFunction.sigma 1 n : ℝ) <
      Real.exp Real.eulerMascheroniConstant * n * Real.log (Real.log n)

def Lagarias : Prop :=
  ∀ n : ℕ, 1 ≤ n →
    (ArithmeticFunction.sigma 1 n : ℝ) ≤
      (harmonic n : ℝ) + Real.exp (harmonic n : ℝ) * Real.log (harmonic n : ℝ)

end ZetaForms
