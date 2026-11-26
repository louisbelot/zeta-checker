import ZetaForms.Divisors

namespace ZetaForms

open Real

theorem sigma_5040 : ArithmeticFunction.sigma 1 5040 = 19344 := by
  rw [ArithmeticFunction.sigma_one_apply]
  decide +kernel

theorem eulerMascheroniConstant_lt : eulerMascheroniConstant < 0.5812 := by
  have h := eulerMascheroniConstant_lt_eulerMascheroniSeq' 128
  have hseq : eulerMascheroniSeq' 128 = (harmonic 128 : ℝ) - log 128 := by
    simp [eulerMascheroniSeq']
  have hlog : (7 : ℝ) * 0.6931471803 < log 128 := by
    rw [show (128 : ℝ) = 2 ^ 7 by norm_num, log_pow]
    have := log_two_gt_d9
    push_cast
    linarith
  have hq : harmonic 128 < (54332302621 : ℚ) / 10 ^ 10 := by
    simp only [harmonic, Finset.sum_range_succ, Finset.sum_range_zero]
    norm_num
  have hr : (harmonic 128 : ℝ) < (54332302621 : ℝ) / 10 ^ 10 := by
    have := (Rat.cast_lt (K := ℝ)).mpr hq
    push_cast at this
    linarith
  rw [hseq] at h
  norm_num at hlog ⊢
  linarith

theorem exp_eulerMascheroniConstant_lt : exp eulerMascheroniConstant < 1.7883 := by
  refine (exp_lt_exp.2 eulerMascheroniConstant_lt).trans_le ?_
  refine (exp_bound' (by norm_num) (by norm_num) (n := 10) (by norm_num)).trans ?_
  norm_num [Finset.sum_range_succ, Nat.factorial]

theorem log_5040_lt : log 5040 < 8.53 := by
  rw [log_lt_iff_lt_exp (by norm_num)]
  refine lt_of_lt_of_le ?_ (sum_le_exp_of_nonneg (by norm_num) 30)
  norm_num [Finset.sum_range_succ, Nat.factorial]

theorem log_log_5040_lt : log (log 5040) < 2.145 := by
  rw [log_lt_iff_lt_exp (log_pos (by norm_num))]
  refine log_5040_lt.trans (lt_of_lt_of_le ?_ (sum_le_exp_of_nonneg (by norm_num) 20))
  norm_num [Finset.sum_range_succ, Nat.factorial]

theorem robin_fails_at_5040 :
    exp eulerMascheroniConstant * 5040 * log (log 5040) <
      (ArithmeticFunction.sigma 1 5040 : ℝ) := by
  rw [sigma_5040]
  calc exp eulerMascheroniConstant * 5040 * log (log 5040)
      ≤ exp eulerMascheroniConstant * 5040 * 2.145 :=
        mul_le_mul_of_nonneg_left log_log_5040_lt.le (by positivity)
    _ < 1.7883 * 5040 * 2.145 :=
        mul_lt_mul_of_pos_right
          (mul_lt_mul_of_pos_right exp_eulerMascheroniConstant_lt (by norm_num)) (by norm_num)
    _ < ((19344 : ℕ) : ℝ) := by norm_num

theorem robin_threshold_sharp :
    ¬ ∀ n : ℕ, 5039 < n →
      (ArithmeticFunction.sigma 1 n : ℝ) <
        exp eulerMascheroniConstant * n * log (log n) := by
  intro h
  have := h 5040 (by norm_num)
  push_cast at this
  linarith [robin_fails_at_5040]

end ZetaForms
