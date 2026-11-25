import Mathlib

namespace ZetaForms

noncomputable def riemannXi (s : ℂ) : ℂ :=
  (s * (s - 1) * completedRiemannZeta₀ s + 1) / 2

noncomputable def liCoeff (n : ℕ) : ℝ :=
  (iteratedDeriv n (fun s : ℂ => s ^ (n - 1) * Complex.log (riemannXi s)) 1).re /
    (n - 1).factorial

def Li : Prop :=
  ∀ n : ℕ, 1 ≤ n → 0 ≤ liCoeff n

end ZetaForms
