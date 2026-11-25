import ZetaForms.RH
import ZetaForms.Li

namespace ZetaForms

example : RH = RiemannHypothesis := rfl

theorem riemannXi_one : riemannXi 1 = 1 / 2 := by
  simp [riemannXi]

theorem riemannXi_eq {s : ℂ} (h0 : s ≠ 0) (h1 : s ≠ 1) :
    riemannXi s = s * (s - 1) / 2 * completedRiemannZeta s := by
  have h1' : (1 : ℂ) - s ≠ 0 := sub_ne_zero.mpr (Ne.symm h1)
  rw [riemannXi, completedRiemannZeta_eq]
  field_simp
  ring

end ZetaForms
