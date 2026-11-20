import Lean  -- expect: import Lean
import Mathlib.Tactic

open Lean Elab Tactic Meta

set_option maxHeartbeats 400000 in  -- expect: set_option maxHeartbeats
theorem slow : (2 : ℕ) ^ 10 = 1024 := by norm_num

theorem plain : 2 + 2 = 5 := sorry  -- expect: sorry

theorem tactic_admit : False := by admit  -- expect: admit

theorem stopped : False := by
  stop  -- expect: stop
  exact absurd rfl id

axiom magic : False  -- expect: axiom

set_option debug.skipKernelTC true in  -- expect: set_option debug.skipKernelTC
theorem unchecked : (1 : ℕ) = 1 := rfl

theorem by_native : 10 < 20 := by native_decide  -- expect: native_decide

theorem by_plus_native : 10 < 20 := by decide +native  -- expect: decide +native

theorem reduced : True := of_eq_true (Lean.ofReduceBool true true rfl)  -- expect: ofReduceBool

macro "trust_me" : tactic => `(tactic| sorry)  -- expect: macro, sorry

elab "close_it" : tactic => do  -- expect: elab
  let g ← getMainGoal
  g.admit  -- expect: MVarId.admit

elab "sneaky" : tactic => do  -- expect: elab
  let g ← getMainGoal
  g.assign (← mkSorry (← g.getType) false)  -- expect: mkSorry

def fake : Expr := mkConst ``sorryAx [levelZero]  -- expect: name-literal sorryAx

macro_rules  -- expect: macro_rules
  | `(tactic| decide) => `(tactic| sorry)  -- expect: sorry

run_cmd logInfo "hello"  -- expect: run_cmd

#eval IO.println "side effect"  -- expect: #eval

initialize registerTraceClass `zeta  -- expect: initialize

@[implemented_by fastImpl]  -- expect: implemented_by
def slowImpl (n : Nat) : Nat := n

@[extern "lean_zeta"]  -- expect: extern
opaque zetaFFI : Nat → Nat  -- expect: opaque

unsafe def peek : Nat := unsafeCast ()  -- expect: unsafe, unsafeCast

partial def loop (n : Nat) : Nat := loop n  -- expect: partial

def interpolated : String := s!"value {(sorry : Nat)}"  -- expect: sorry

run_cmd Lean.modifyEnv fun env => env  -- expect: run_cmd, modifyEnv

def spawn : IO Unit := do let _ ← IO.Process.output { cmd := "ls" }  -- expect: Process

set_option autoImplicit true  -- expect: set_option autoImplicit

notation "ℛ" => True  -- expect: notation

theorem after_string : False := by
  let s := "--"; exact sorry  -- expect: sorry

theorem after_char : False := by
  let c := '"'
  exact sorry  -- expect: sorry

theorem after_block_open : False := by
  let s := "/-"
  exact sorry  -- expect: sorry

theorem after_raw : False := by
  let r := r#"a "quoted" -- b"#; exact sorry  -- expect: sorry

/- outer /- inner -/ sorry -/ theorem after_nested : False := sorry  -- expect: sorry

theorem primes (f' : ℕ → ℕ) (x' : ℕ) : f' x' = f' x' := by
  have c := 'a'; exact sorry  -- expect: sorry

#exit  -- expect: #exit
