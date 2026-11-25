import Mathlib

namespace ZetaForms

def GRH : Prop :=
  ∀ {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N) (s : ℂ),
    χ.LFunction s = 0 → 0 < s.re → s.re < 1 → s.re = 1 / 2

def GRHPrimitive : Prop :=
  ∀ {N : ℕ} [NeZero N] (χ : DirichletCharacter ℂ N), χ.IsPrimitive → ∀ s : ℂ,
    χ.LFunction s = 0 → 0 < s.re → s.re < 1 → s.re = 1 / 2

end ZetaForms
