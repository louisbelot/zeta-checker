import Mathlib

namespace ZetaForms

def RH : Prop := RiemannHypothesis

def HalfPlane : Prop :=
  ∀ s : ℂ, 1 / 2 < s.re → riemannZeta s ≠ 0

end ZetaForms
