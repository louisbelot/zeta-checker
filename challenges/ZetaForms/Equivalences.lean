import ZetaForms.RH
import ZetaForms.GRH

open Complex

namespace ZetaForms

theorem trivial_re {s : ℂ} (h : ∃ n : ℕ, s = -2 * (n + 1)) : s.re < 0 := by
  obtain ⟨n, rfl⟩ := h
  have e : (-2 * ((n : ℂ) + 1)) = ((-2 * ((n : ℝ) + 1) : ℝ) : ℂ) := by push_cast; ring
  rw [e, ofReal_re]
  have := (Nat.cast_nonneg n : (0 : ℝ) ≤ n)
  linarith

theorem halfPlane_of_rh (h : RiemannHypothesis) : HalfPlane := by
  unfold RiemannHypothesis at h
  unfold HalfPlane
  intro s hs hz
  by_cases h1 : s = 1
  · subst h1
    exact riemannZeta_one_ne_zero hz
  · have triv : ¬∃ n : ℕ, s = -2 * (n + 1) := fun ht => by
      have := trivial_re ht
      linarith
    have := h s hz triv h1
    linarith

theorem zeta_one_sub_eq_zero {s : ℂ} (hz : riemannZeta s = 0) (hlt : s.re < 1 / 2)
    (htriv : ¬∃ n : ℕ, s = -2 * (n + 1)) : riemannZeta (1 - s) = 0 := by
  have hs0 : s ≠ 0 := by
    rintro rfl
    rw [riemannZeta_zero] at hz
    norm_num at hz
  have hn : ∀ n : ℕ, (1 - s) ≠ -n := by
    intro n hn
    have e : s = 1 + n := by linear_combination -hn
    have hre : s.re = 1 + n := by rw [e]; simp
    have := (Nat.cast_nonneg n : (0 : ℝ) ≤ n)
    linarith
  have h1 : (1 - s) ≠ 1 := by
    intro e
    apply hs0
    linear_combination -e
  have hπ : (Real.pi : ℂ) ≠ 0 := ofReal_ne_zero.mpr Real.pi_ne_zero
  have hpow : (2 * (Real.pi : ℂ)) ^ (-(1 - s)) ≠ 0 := by
    rw [cpow_def_of_ne_zero (mul_ne_zero two_ne_zero hπ)]
    exact exp_ne_zero _
  have hcos : cos (Real.pi * (1 - s) / 2) ≠ 0 := by
    rw [Ne, Complex.cos_eq_zero_iff]
    rintro ⟨k, hk⟩
    have hmul : (Real.pi : ℂ) * ((1 - s) - (2 * k + 1)) = 0 := by linear_combination 2 * hk
    rcases mul_eq_zero.mp hmul with h0 | h0
    · exact hπ h0
    have hs : s = -2 * (k : ℂ) := by linear_combination -h0
    have e : (-2 * (k : ℂ)) = ((-2 * (k : ℝ) : ℝ) : ℂ) := by push_cast; ring
    have hre : s.re = -2 * (k : ℝ) := by rw [hs, e, ofReal_re]
    have hk1 : (-1 : ℝ) < k := by linarith
    have hk1' : -1 < k := by exact_mod_cast hk1
    rcases (show k = 0 ∨ 0 < k by omega) with rfl | hpos
    · apply hs0
      rw [hs]
      simp
    · obtain ⟨n, rfl⟩ : ∃ n : ℕ, k = n + 1 := ⟨(k - 1).toNat, by omega⟩
      apply htriv
      exact ⟨n, by rw [hs]; push_cast; ring⟩
  have fe := riemannZeta_one_sub hn h1
  rw [sub_sub_cancel, hz] at fe
  rcases mul_eq_zero.mp fe.symm with h | h
  · rcases mul_eq_zero.mp h with h | h
    · rcases mul_eq_zero.mp h with h | h
      · rcases mul_eq_zero.mp h with h | h
        · norm_num at h
        · exact absurd h hpow
      · exact absurd h (Gamma_ne_zero hn)
    · exact absurd h hcos
  · exact h

theorem rh_of_halfPlane (h : HalfPlane) : RiemannHypothesis := by
  unfold HalfPlane at h
  unfold RiemannHypothesis
  intro s hz htriv _
  by_contra hne
  rcases lt_or_gt_of_ne hne with hlt | hgt
  · exact h (1 - s) (by rw [sub_re, one_re]; linarith) (zeta_one_sub_eq_zero hz hlt htriv)
  · exact h s hgt hz

theorem halfPlane_iff_rh : HalfPlane ↔ RiemannHypothesis :=
  ⟨rh_of_halfPlane, halfPlane_of_rh⟩

theorem rh_of_grh (h : GRH) : RiemannHypothesis := by
  unfold GRH at h
  apply rh_of_halfPlane
  unfold HalfPlane
  intro s hs hz
  have hre : s.re < 1 := not_le.mp fun hge => riemannZeta_ne_zero_of_one_le_re hge hz
  have hz' : (1 : DirichletCharacter ℂ 1).LFunction s = 0 := by
    rw [DirichletCharacter.LFunction_modOne_eq]
    exact hz
  have := h (1 : DirichletCharacter ℂ 1) s hz' (by linarith) hre
  linarith

end ZetaForms
