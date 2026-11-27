import Mathlib

namespace ZetaForms

open Real

noncomputable def deBruijnPhi (u : ℝ) : ℝ :=
  ∑' n : ℕ, (2 * π ^ 2 * ((n : ℝ) + 1) ^ 4 * Real.exp (9 * u) -
      3 * π * ((n : ℝ) + 1) ^ 2 * Real.exp (5 * u)) *
    Real.exp (-π * ((n : ℝ) + 1) ^ 2 * Real.exp (4 * u))

noncomputable def deBruijnH (t : ℝ) (z : ℂ) : ℂ :=
  ∫ u in Set.Ioi (0 : ℝ), ((Real.exp (t * u ^ 2) * deBruijnPhi u : ℝ) : ℂ) * Complex.cos (z * u)

def DeBruijnNewman : Prop :=
  ∀ t : ℝ, 0 < t → ∀ z : ℂ, deBruijnH t z = 0 → z.im = 0

end ZetaForms
