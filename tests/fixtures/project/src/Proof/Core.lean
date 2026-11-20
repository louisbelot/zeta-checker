import Mathlib

namespace Proof

theorem rh : RiemannHypothesis := sorry

theorem grh (N : ℕ) [NeZero N] (χ : DirichletCharacter ℂ N) (hχ : χ.IsPrimitive) (s : ℂ)
    (h0 : 0 < s.re) (h1 : s.re < 1) (hz : DirichletCharacter.LFunction χ s = 0) :
    s.re = 1 / 2 := by
  sorry

end Proof
