import Mathlib

open MeasureTheory

namespace ZetaForms

def BaezDuarte : Prop :=
  ∀ ε : ℝ, 0 < ε → ∃ (N : ℕ) (c : ℕ → ℝ),
    ∫⁻ t in Set.Ioi (0 : ℝ),
        ENNReal.ofReal ((Set.indicator (Set.Ioc (0 : ℝ) 1) (fun _ => (1 : ℝ)) t -
          ∑ k ∈ Finset.range N, c k * Int.fract (1 / ((k + 1 : ℝ) * t))) ^ 2) <
      ENNReal.ofReal ε

end ZetaForms
