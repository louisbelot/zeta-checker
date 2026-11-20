-- sorry admit axiom native_decide stop
/-- A docstring that says sorry and axiom and uses `native_decide`. -/
theorem decoy_doc : True := trivial

/-! Module doc: set_option debug.skipKernelTC true, run_cmd, #eval -/

/- outer /- nested sorry -/ still a comment: admit, axiom, implemented_by -/

def s1 : String := "sorry"
def s2 : String := "contains -- not a comment, then sorry"
def s3 : String := r#"raw "sorry" with quotes"#
def s4 : String := "escaped \" sorry \" inside"
def s5 : String := s!"text with sorry and code {1 + 1}"
def s6 : String := "/- not a comment -/ sorry"
def c1 : Char := 's'
def c2 : Char := '\''
def sorry_free : Nat := 0
def axiomatic : Nat := sorry_free
theorem no_admit_here' : True := trivial
def admitted : Nat := 1
def «sorry» : Nat := 3  -- expect: escaped-name
def «a--b» : Nat := 4
def extern_count : Nat := 2
def usesExtern (extern : Nat) : Nat := extern
def native : Nat := 3
def partialSums : Nat := 0
def opaqueish : Nat := 0
def stopwatch : Nat := 0
def ref : Lean.Name := `macro
