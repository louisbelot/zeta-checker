# DEVLOG

## 2026-11-20

First working day. The package, its CI and the whole acquisition side, plus the first
static checks on Lean code.

**Fetching.** `manifest.json` lists the 16 files (remark.pdf, the 14 archive parts,
Masullo's PDF) with size, SHA-256, ETag and Last-Modified. `fetch --record` hashed
the local copies and `fetch --rehash` streamed all 246,277,664 bytes again from the
two servers: every hash matched. The downloader retries 5xx, 408, 425 and 429 with
exponential backoff, fails fast on other 4xx, resumes with Range when the server
answers 206 and starts over when it answers 200. That second case is real: alpo.ge
ignores Range on the archive parts and gives no Content-Length on HEAD. The tests use a
fake opener that drops connections a third of the way in, lies about Content-Length and
returns 503 twice, so none of them touch the network.

**Extraction.** The parts are read through a `RawIOBase` that concatenates files, so
the 239 MB archive is never joined on disk. Pass one decompresses the stream (the gzip
check counts members and catches truncation and trailing junk) and vets every tar
member. Pass two runs only on a clean listing and writes files with mode `xb`. The
released archive passed: 175,190 regular files, no directory entries, no links, no
special files, nothing absolute or with `..`, no case collisions, 1,270,753,280 bytes
of tar.

The first real extraction died on a 270-character path. Long paths are off in this
machine's registry and flipping a system setting for one tool is the wrong fix, so
`fs.long` adds the `\\?\` prefix and every walk and write goes through it. `fs.walk`
also raises on unreadable folders instead of skipping them, since `os.walk` silently
drops what it can't list. A test now builds a 300-character member and runs extract,
inventory and scan over it.

**PDF text.** pdftotext when present (it handles the manuscript's 940 pages in a few
seconds), pypdf otherwise. Pages are separated by `--- page N ---` lines so `find`
can report page numbers, and the outline goes to a separate file. The PDF tests build
a three-page PDF with an outline byte by byte.

**Lake config.** `config` reads lean-toolchain, lakefile.toml and lake-manifest.json:
whether the toolchain is an official release tag, whether each `require` rev matches
the manifest, Lean options and arguments, any key that brings native code
(`precompileModules`, `extern_lib`, link args), which `lean_lib` globs cover which
modules (Lake's `.+` and `.*` semantics), modules no lib builds, and any file that is
not Lean source or Lake config, with ELF, PE, Mach-O and olean magic numbers.

**Masker and scanner.** The design choice that matters: instead of a token stream, the
masker replaces comments and literal contents with spaces and keeps every newline and
every character offset. Regexes then run over code only, at C speed, and line numbers
come straight from offsets. Lean's identifier rules are copied from `isIdFirst` and
`isIdRest` (ASCII letters, `_`, `'`, `!`, `?`, Greek except λ Π Σ, the letter-like
block that holds ℂ ℕ ℝ, subscripts). The scanner prefilters each file with one combined
regex on the raw text, which is sound because masking can only remove matches, never
create them.

**Statements.** Declarations are parsed with their namespace (namespace, section,
mutual, `end` with dotted names, `_root_`), signatures end at `:=`, `where`, a leading
`|` or the next command at column 0. `shape` turns a statement into binders, premises
and conclusion, treating `(_ : P)` as a premise and stopping at an unparenthesized
binder like `∃`, which in Lean extends to the end of the expression. `compare` aligns
two shapes with difflib and diffs mismatched items token by token. The reference
statement is Mathlib's `RiemannHypothesis` at commit 0df444a3, which is the upstream
tag v4.33.1.

**Imports.** `imports` builds the import graph from masked headers (so commented-out
imports don't count, and `public`, `meta` and `import all` from the module system
do), computes the cone of the statement modules and splits a scan's hits into inside
and outside that cone.

**Reading from the tarball.** The first full scan read the extracted files one by one
and crawled: another job had all 16 cores busy, and on Windows every open of a small
file waits for the antivirus. After 15 minutes it had used about a minute of CPU. The
scanner, inventory, import graph and statement trace now take `(path, bytes)` pairs, and
`--archive` feeds them straight from the hashed parts, 14 opens instead of 175,187. On
the same loaded machine the whole scan took 1m56s, the inventory 19s. A test checks
that archive mode and directory mode give identical reports.

**A false positive.** The first real run flagged one `stop`. It was a structure field,
`stop : κ n = tau`, which Lean accepts as a name. `stop` and `admit` followed by a colon
now count as names (`(sorry : T)` still counts, since that is a type ascription), and
the decoy file has a structure with both fields.

All of it ran on the released files today. The outputs are in the local workspace and
stay there until they have been read through.

Next: a Linux CI job that builds only the cone of the main theorems with no secrets and
prints `#print axioms`, after measuring what that build needs; then comparator with a
challenge file holding Mathlib's statement.

## 2026-11-20, second session

Three new pieces: a declaration graph built from source, a triage pass for long
manuscripts, and a check on the context the statement files are elaborated in.

**Statement context.** `statements` now lists, for each root module, which of its
imports are project modules and every `instance`, `attribute`, `set_option`, notation,
macro, `open` or `variable` command in it (comments and strings masked first). A
statement file that imports only Mathlib and has none of these can't have its meaning
changed by a project instance, coercion or notation, because none of them is in scope
when it is elaborated. Anything stated elsewhere in terms of it still has to match it in
the kernel, so that is the file worth checking by hand.

**Declaration graph.** `decls` turns every theorem, def, structure and instance into a
node and every resolvable name in its signature or proof into an edge. Resolution
follows Lean's lookup order: the declaration's namespaces from the innermost out (with
the prefix of a dotted declaration name counted as a namespace, the way Lean opens it
for the body), then the file's `open`s, then the prefix of a dotted name, so a field or
constructor reference lands on its structure. Locally bound names are dropped before
lookup: binders after `fun`, `∀`, `∃`, big operators, `intro`, `obtain`, `have`, `let`,
`set`, `choose`, `with`, binder groups and match arms. Tactic names are dropped too.
Without that, a root-level `def change` in some file collected an edge from every proof
that used the `change` tactic, and a root-level `hm` from every proof with a hypothesis
called `hm`. Both showed up in the first full run as tiny nodes at the top of the tree.
References come from the whole declaration text, so `where` bodies and structure fields
count too; the first version only read what followed `:=` and missed them.

It takes two passes so memory stays flat: pass one records names, pass two resolves.
Edges go in one flat `array('i')` with offsets (CSR), about 4 bytes each, so a graph
with millions of edges fits in a few hundred megabytes of Python. Over the hashed
archive the whole thing (two decompressions of 1.27 GB of tar, two parses of every
file, resolution, dominators) takes about five and a half minutes on this machine
(5m32s for the last run).

The output is the dominator tree of the part reachable from the root modules, computed
with Cooper, Harvey and Kennedy's iterative algorithm ("A Simple, Fast Dominance
Algorithm", 2001): number nodes in DFS postorder, then repeat over reverse postorder,
setting each node's idom to the intersection of its processed predecessors' idoms,
walking two fingers up the current tree until they meet. It converges in a few passes on
graphs like this and needs nothing but arrays. A node's subtree in that tree is the
set of declarations that can only be reached through it, so weighting nodes by source
lines shows where a proof funnels. The tests check it against a brute-force definition
(d dominates v iff v is unreachable once d is removed) on 300 random graphs, and on
an irreducible graph, a loop of two nodes entered from two sides, so that only the entry
dominates either of them.

Limits, also in the README: instances found by type class search, lemmas used by
`simp` or tactics without being named, and generalized field notation are invisible
from source. "Not reached by name" is a lower bound on what the proof uses, not a list
of dead code.

**Manuscript triage.** `manuscript` indexes numbered results from the page-numbered
text, with titles that can contain one or two levels of parentheses. pdftotext's layout
mode keeps indentation, which helped: headers are indented, while a line at the margin
holding only `Theorem 3.1.2.4.` is a sentence that wrapped. The first version took
those as headers and reported numbers declared three times; the rule now is that a
margin line needs a title or text after the period. A reference such as
`Lemma 2.2.2.1(3) provides` is never a header because the title has to follow a space.

Cross-references are assigned to the result whose header precedes them, with citation
brackets blanked out first so `[AB, Lemma 1]` doesn't count. It reports numbers
referenced but never declared, numbers declared twice, gaps in each sequence (checked
against equation labels, which share the counter), and markers in four groups:
unresolved references (`??`), editorial phrases, deferrals and omitted proofs, plus
footnotes that are notes to the author ("3Check this." in pdftotext's output, the
footnote number glued to the text). The bibliography is parsed from the outline's
Bibliography page and every bracket citation is matched against its keys.

Next: the size of a sandbox build compared with Mathlib's, then the Linux CI job that
builds the main theorems' cone with no secrets and prints `#print axioms`, and
comparator with a challenge file holding Mathlib's statement.

## 2026-11-23

An `audit` command that runs every static check on a Lean project and writes one
report, a suite of planted failures it has to catch, and tracking of the upstream
files against an independent verification effort.

**Cross-check.** The Lean community has a public comparator setup for the development
(leanprover-community/riemann-hypothesis, notes in `verification/`). Its notes publish
the SHA-256 of the 14 parts joined: `9631b4f0...f49c7fc`, 239,275,554 bytes. Hashing
the local parts as one stream gives the same digest, so both audits read the same
bytes. Their static scan and this one agree on `addDecl` in one file and on the five
`BuildAid` files that call `modifyEnv`. They count 33 `run_tac`; a plain text search
here finds 32 in 16 files, the same as the scanner, so the gap is not masking. They
also describe two tactics that close a goal with `MVarId.assign`, which skips the
elaborator's type check and leaves the kernel as the only check. The scanner had no
rule for that. It has one now (`MVarId.assign`, medium, only on a qualified call so a
local named `assign` doesn't count), and on the development it finds the three call
sites the notes describe.

Their build numbers also settle where a kernel check can run: 48 cores and 503 GB of
RAM on course for 7 to 10 hours, Lake setup files of about a terabyte unless deleted
during the build, an export of 61.6 GB that peaked at 163 GB. A free GitHub runner has
16 GB and 14 GB of disk, so no sandbox workflow was added. The README says so.

**Tracking upstream.** The manifest now records the joined digest of a split archive,
and `extract` checks it before reading a member (`--record` stores it the first time).
`fetch --upstream` also asks for the part after the last one. The server returns 200
and an HTML page for any path, so a status code says nothing; the probe reads the
content type. Run today: all 16 files unchanged, `part15` is an HTML page.

**audit.** One pass that loads the Lake config, finds the root modules (the `roots` of
each `lean_lib` without globs), parses their theorems, builds the import graph and its
cone, scans every file for hatches and traces every name the statements use. Findings
have a severity, a code, a place and the text, sorted on all five fields so the JSON is
the same however the files are read. The exit code is 2 for critical, 1 for high.

The import cone sets the severity. A hatch outside the cone is `low`, since nothing the
statements import can reach it; inside, it keeps the scanner's risk. Options set to
`false` or `0` are counted, not listed: on the development every one of the 11,203
`set_option autoImplicit` lines sets it to `false`, which only makes elaboration
stricter.

Hypotheses on the root theorems are checked one by one: `False`, `¬ True` or `⊥` is
vacuous, a hypothesis equal to the conclusion or naming the statement is circular, and a
hypothesis using a project-declared name is high. The first version looked for that name
anywhere in the cone and flagged `DirichletCharacter.LFunction` in two GRH statements,
because the development declares a `def LFunction` in two namespaces of its own. That was
wrong in principle: those statements are Props defined in `Statements.lean`, which
imports only Mathlib, so nothing from the project is in scope where their names are
resolved. Each theorem now carries the file its statement is elaborated in (the Prop's
file when it unfolds one), and a declaration is high only if its module is in that
file's import cone.

Lake options get the same ranking as `set_option`, read from `leanOptions` (nested
tables flattened to dotted names) and from `-Dname=value` in `moreLeanArgs` and
`weakLeanArgs`. `debug.skipKernelTC = true` in a lakefile would turn the kernel off for
a whole library and never show up in a `.lean` file.

A bug the self-review caught: findings were deduplicated through a set, so two hatches
of the same rule on one line collapsed into one. The test that reads the files in
reverse order now also counts them.

**Planted failures.** `tests/test_audit.py` writes small fake projects, each with one
trick: a `False` hypothesis, `¬ True →`, RH assumed to prove RH, a hypothesis defined in
the project, an extra `axiom`, `skipKernelTC` in source, in `leanOptions` and as a `-D`
argument, `sorry` behind a macro, `native_decide`, a goal closed by `MVarId.assign`, a
project `riemannZeta` the statement can see, notation over the statement's name, the
critical line moved to 1/3, no RH theorem, a `lakefile.lean`, a module named like a
Mathlib file, a manifest that disagrees with the pin and an unofficial toolchain. All
are flagged at medium or above. A clean project is the control and gives nothing.

On the extracted development the audit took 3m15s on the second run (6m22s the first,
with another scan running alongside); the findings stay in
the workspace with the rest of the report.

Next: Lean challenge files for the standard equivalent forms of RH (Robin, Lagarias,
Li, Nyman-Beurling), checked in CI against Mathlib only, and the manuscript triage made
generic for any PDF claim.

## 2026-11-24

A statement library of RH and its standard equivalents, written in Lean against the
pinned Mathlib and built in CI, the audit taught to recognise them, and numerical
checks of each criterion against published values.

**The Lean side.** `challenges/` is a Lake project on Mathlib v4.33.1, the same commit
the development pins (the manifest is Mathlib's own, with the packages marked
inherited). `ZetaForms` has one `def ... : Prop` per form: `HalfPlane` (no zeros with
`1/2 < re s`), `GRH`, `GRHPrimitive` and `GRHHalfPlane`, `Robin`, `Lagarias`, `Mertens` (Littlewood's
`M(x) = O(x^(1/2+ε))`), `Li` and `BaezDuarte`. Every Mathlib name was looked up in a
shallow clone of the pinned tag before writing, and the first CI run built all of it.
The build is 2.5 minutes, nearly all of it the cache download.

Writing them down meant dealing with Mathlib's junk values. `completedRiemannZeta 1`
is a number, so the textbook `ξ(s) = s(s-1)/2 · Λ(s)` is `0` at `s = 1` instead of
`1/2`, is not differentiable there, and `deriv` at 1 returns 0. A Li criterion on top of
it would have λ_1 = 0 for free. `riemannXi` is defined from the entire
`completedRiemannZeta₀` as `(s(s-1)Λ₀(s) + 1)/2`, using
`Λ = Λ₀ - 1/s - 1/(1-s)`, which Mathlib states for every s. `Sanity.lean` proves
`riemannXi 1 = 1/2` and that `riemannXi` equals the textbook ξ off 0 and 1. The
Báez-Duarte distance is a lower Lebesgue integral, because the Bochner integral of a
non-integrable function is 0 and `0 < ε` would make the statement trivial. The GRH strip
is open, which keeps out the pole of the trivial character and the zeros on `re s = 0`
that an imprimitive character gets from its Euler factors.

`Challenges/` has one comparator challenge per form and `comparator/` the configs. The
workflow checks that `ZetaForms` builds with no `sorry` and each challenge with exactly
one.

**Proofs.** `Equivalences.lean` proves `HalfPlane ↔ RiemannHypothesis` and
`GRH → RiemannHypothesis`. There is no Lean on this machine, so the lemma names were
grepped from the pinned Mathlib clone and the proofs were checked only in CI; both
built on the first run, and the second run only removed a dead `first` branch and a
deprecated `push_neg` that the linters pointed at. The interesting step is the left
half of the strip. A zero with `re s < 1/2` gives a zero at `1 - s` through
`ζ(s) = 2 (2π)^(s-1) Γ(1-s) cos(π(1-s)/2) ζ(1-s)` unless a factor vanishes. The power
and Γ never do here, and `cos(π(1-s)/2) = 0` forces `s = -2k`: for k ≥ 1 that is a
trivial zero, which RH excludes, k = 0 is `s = 0` where `ζ = -1/2`, and k < 0 is right
of the line. GRH → RH specializes to the trivial character mod 1, whose `LFunction` is
`riemannZeta` by `LFunction_modOne_eq`, and uses non-vanishing on `re s ≥ 1` to land in
the strip.

**audit.** A root theorem is matched against the library before the old riemannZeta
fallback: by name (`theorem x : ZetaForms.Robin`), by exact tokens, or by key constants
(`sigma` and `eulerMascheroniConstant` for Robin, `sigma` and `harmonic` for Lagarias,
`LFunction` plus `IsPrimitive` for primitive GRH). Key constants are collected through
the project's own definitions, so a Li statement written as `0 ≤ lam n` with `lam`
defined via `iteratedDeriv` still matches. An exact match is an `info` finding naming
the form and the paper; anything else is compared line by line like an RH restatement.
Moving Robin's threshold from 5040 to 2520 gives
``premise: `2520` here, `5040` in reference``. Running the audit on `challenges/` itself
is now a test: ten theorems (RH and the nine forms), each matched exactly, ten `sorry` findings and nothing
else at medium or above.

A bug found on the way: `lake.roots` skipped a `lean_lib` with no `roots` key, but Lake
defaults the roots to the library's name. The development lists its roots explicitly,
so its audit was unaffected.

**criteria.** Robin's exceptions up to 10^5 are exactly OEIS A067698 (27 terms, the
last 5040). Lagarias holds up to 10^5 with equality only at n = 1; the closest call is
n = 12 at 1.1% slack.

The Li coefficients come from the Keiper-Li series `log ξ(1/(1-z)) = log ξ(0) +
Σ λ_n z^n/n`. The map `z ↦ 1/(1-z)` sends the unit disk onto `re s > 1/2`, so under RH
the series converges on the whole disk, with the zeros on its boundary. Sampling
`log ξ` on `|z| = 0.8` at 512 points, unwrapping the phase and taking a DFT gives the
coefficients; the aliasing error is about `0.8^512`, and the cancellation costs
`0.8^-n` relative to 30-digit arithmetic. If the unwrapped phase does not close the
loop, there is a zero inside the circle and the function raises. Against Maślanka's
table (arXiv:math/0402168) every printed digit agrees for n = 1 to 15 and at n = 100
(118.603775377). λ_1 and λ_2 also agree to 1e-14 with their closed forms,
`1 + γ/2 - log(4π)/2` and `1 + γ - γ² + π²/8 - log 4π - 2γ_1`. A first version of the
test used 128 points and was off by 5e-13 at λ_1, which is the `0.8^128` aliasing term.

For Báez-Duarte, the Gram matrix of `{1/(kt)}` in `L²(0,∞)` has Vasyunin's closed form
with cotangent sums, and `⟨1_(0,1], {1/(kt)}⟩ = (1 - γ + log k)/k`. The tests check
Vasyunin against direct integration (in `u = 1/t` both functions are linear on every
unit interval, so each piece integrates exactly, plus the periodic tail), to 1e-6.
`d_N²` comes from a Cholesky factorization grown one row at a time, so all N up to 60
cost one O(N³) pass, in 2 seconds at 40 digits. `d_N² log N` sits near 0.047 from N =
7 on, just above the 0.04619 that Báez-Duarte, Balazard, Landreau and Saias give as the
lower limit when the zeros are simple.

**On the development.** The first run of the new audit on the extracted development
reported 11 more `medium` findings than on 2026-11-23, all on the three GRH statements
in `src/Main.lean`. Two of the causes do not change the proposition: `{N : ℕ}` against
`(N : ℕ)`, and `χ.LFunction s` against `DirichletCharacter.LFunction χ s`. `compare`
now drops binder brackets and rewrites `v.f` to `T.f v` when `v` is bound with head
type `T` and the other side spells it that way. The third was the zero hypothesis placed
after the strip bounds instead of before; a premise that only moved is now an `info`
finding (`statement-reordered`). The rest were on
`LFunction_ne_zero_of_half_lt_re`, compared against the strip form because it is the
half-plane form of GRH and the library did not have one. It has `GRHHalfPlane` now, and with several GRH forms sharing `LFunction`
the lookup now breaks ties by token similarity.

Final run, 3m31s on a warm cache (17m36s cold): critical 0, high 44, medium 45, low 2,
info 15. Against 2026-11-23 the only differences are three new `info` findings: the
half-plane theorem states `ZetaForms.GRHHalfPlane` exactly, and the two strip theorems
match `GRH` and `GRHPrimitive` up to the position of the zero hypothesis.

Next: Robin failing at 5040 proved in Lean, a comparator run end to end on a small
solution (the HalfPlane equivalence), and certified interval enclosures for the Li
coefficients.
