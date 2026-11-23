# zeta-checker

Tools for checking claimed proofs of the Riemann Hypothesis.

Two claims came out on 2026-11-20. Levent Alpöge released a Lean 4 development
with a short note ([alpo.ge/remark.pdf](https://alpo.ge/remark.pdf)), and Ravi
Vakil posted Alessandro Masullo's manuscript on the Generalized Riemann
Hypothesis ([announcement](https://math216.wordpress.com/2026/11/20/hurried-announcement-alessandro-masullo-grh/)).
This repo checks them mechanically: what exactly the Lean code states, whether
anything in it gets around the kernel, how the proof is put together, and what
the manuscript claims, section by section.

It doesn't host either author's files. The scripts download them, check them
against recorded hashes and work on local copies.

Nothing here judges whether the mathematics is right. That is for the people
reading the proofs. Every number reported comes with the command that produced
it.

## What runs where

Everything in this repo reads files as text. It never builds, elaborates or runs
the downloaded Lean code: a lakefile, a macro, `#eval`, `run_cmd` or `initialize`
can execute arbitrary programs, so anything that executes the development belongs
in a throwaway Linux sandbox, not on a laptop.

A kernel check of this development doesn't fit on a free GitHub runner (4 vCPU,
16 GB, 14 GB of disk, 6 hours per job). The comparator setup above reports a build on
48 cores and 503 GB of RAM on course for 7 to 10 hours, Lake setup files totalling
around a terabyte if they are not deleted during the build, and an independent export
of 61.6 GB that peaked at 163 GB of memory. So this repo stops at static checks and
points to those runs for the kernel replay.

## Install

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Python 3.10 or newer. `pdftotext` (poppler) is used for PDFs when it is on the
PATH, with pypdf as the fallback.

All commands take `-w/--workspace`, a folder outside the repo for downloads and
outputs (or set `ZETA_CHECKER_WORKSPACE`). Run anything that reads the downloads
with `python -I` so nothing from the current folder gets imported.

## The pipeline

```
zeta-checker fetch --record             download into <workspace>/downloads, hash, record
zeta-checker fetch                      verify local files against manifest.json
zeta-checker fetch --rehash             stream every source again and compare hashes
zeta-checker extract --list             check the split tarball without writing anything
zeta-checker extract                    extract into <workspace>/alpoge_lean
zeta-checker pdftext <pdf>...           page-numbered text and outline into <workspace>/text
zeta-checker find <txt> <regex>         grep that prints page numbers
zeta-checker inventory <dir>            files, lines and bytes by extension and folder
zeta-checker config <lean-project>      toolchain, pins, Lake options, lib coverage
zeta-checker scan <lean-project>        escape hatches, grouped by risk
zeta-checker statements <lean-project>  top-level statements traced to their definitions
zeta-checker imports <lean-project>     import graph and the cone of the statement modules
zeta-checker decls <lean-project>       declaration graph and its dominator tree
zeta-checker manuscript <txt>           numbered results, cross-references, markers, citations
zeta-checker audit <lean-project>       every static check on a project, one JSON report
```

`inventory`, `scan`, `statements`, `imports` and `decls` also take `--archive STEM --under DIR`
to read the `.lean` files straight out of the hashed tarball instead of the extracted
copy. On Windows that matters: opening 175,000 small files one by one is slow when an
antivirus checks each open, while the tar stream is 14 opens.

`manifest.json` holds the URL, size, SHA-256 and the server's ETag and
Last-Modified for each of the 16 files. A rerun of `fetch` fails if a local file no
longer matches, and `fetch --upstream` flags a changed ETag or size on the server.
`extract` also hashes the 14 parts as one stream before it reads a member, and the
manifest records that joined digest: 239,275,554 bytes, SHA-256
`9631b4f020199e580ba86178cb56c6e9b09f690c2369a80dc4334aa93f49c7fc`. The community's
comparator setup
([leanprover-community/riemann-hypothesis](https://github.com/leanprover-community/riemann-hypothesis),
`verification/NOTES.md`) publishes the same digest for its copy, so both read identical
bytes.
`fetch --upstream` also asks for the part after the last one. The server answers any
path with an HTML page and status 200, so the probe looks at the content type, not the
status, before it reports a new part.

The alpo.ge parts come without a Content-Length on HEAD and the server ignores
Range requests for them, so the downloader verifies sizes from the GET response,
resumes with Range where a server allows it and restarts where it doesn't.

## Safe extraction

The archive is 14 parts that concatenate into one gzip stream. `extract` reads the
parts through a concatenating reader, so no joined copy is written. It makes two
passes. The first decompresses everything and checks every member: symlinks, hard
links, device files, FIFOs, absolute paths and `..` components are refused, and so
are names that would misbehave on Windows (reserved names like `aux.lean`, `:` and
other forbidden characters, trailing dots) and names that collide case-insensitively
or where a file and a folder share a path. The gzip CRC is checked to the end of the
stream. Only a clean listing gets a second pass, which writes regular files with
exclusive-create, so nothing already on disk is overwritten.

Some paths in the development are longer than 260 characters once they sit under a
workspace folder. Windows refuses those unless long paths are enabled system-wide,
so every write and walk goes through `\\?\` extended-length paths instead.

## The escape-hatch scanner

A grep for `sorry` is easy to fool in both directions: the word sits in comments and
docstrings, and a real `sorry` can hide after a string that contains `--`. The
scanner first masks a Lean file the way Lean's own tokenizer would see it, then
matches on code only. The masker handles nested `/- -/` comments, doc comments,
string escapes and gaps, raw strings `r#"..."#`, interpolated strings (`s!`, `m!`,
`f!`, where the `{...}` parts are code), character literals versus primes in names
like `f'`, and `«guillemet»` names, which may legally contain `--` or `/-`.

The rules come from the Lean reference's guide to validating a proof, the
comparator tool and the usual ways to slip a proof past `#print axioms`:

| group | what it catches |
|---|---|
| unproven | `sorry`, `admit`, `stop`, `sorryAx`, `mkSorry`, `MVarId.admit` |
| axioms | every `axiom` declaration, with its name |
| kernel | `set_option debug.skipKernelTC`, `addDecl`, `addDeclWithoutChecking`, `modifyEnv`, `setEnv` |
| compiler | `native_decide`, `decide +native`, `Lean.ofReduceBool`, `trustCompiler`, `@[implemented_by]`, `@[extern]`, `@[csimp]` |
| unchecked | `opaque`, `unsafe`, `partial`, `unsafeCast`, `MVarId.assign` |
| meta | `macro`, `macro_rules`, `elab`, `syntax`, `notation`, `infix`, name literals like ``` ``sorryAx ``` |
| exec | `#eval`, `run_cmd`, `initialize`, `IO.Process` |
| options | every `set_option`, ranked by what the option can change |

`MVarId.assign` closes a goal with a term the elaborator never checked against the
goal's type. That is sound as long as the kernel checks the finished declaration, but
it means the kernel is the only check, so those proofs are the ones to replay with an
independent checker. The rule came from comparing this scanner with the static scan
in the community's comparator setup, which lists two such tactics in the development.

Attribute names only count inside `@[...]` or `attribute [...]`, and an escaped
`«sorry»` is a plain identifier, reported separately. The tests plant every hatch in
`tests/fixtures/lean/planted.lean`, including a `sorry` inside a macro and one
inside an interpolated string, and put decoys in `decoys.lean`; each expected hit is
written next to its line, so the test is the file itself. Run on the fixtures:

```
$ zeta-checker scan tests/fixtures/lean --risk critical --show 1
2 files, 126 lines, 4126 bytes scanned
risk      group      rule                           hits  files
critical  unproven   sorry                            10      1
critical  unproven   MVarId.admit                      1      1
critical  unproven   admit                             1      1
critical  axioms     axiom                             1      1
critical  unproven   mkSorry                           1      1
critical  kernel     set_option debug.skipKernelTC     1      1
critical  unproven   stop                              1      1
high      exec       Process                           1      1
high      compiler   decide +native                    1      1
...
[critical] sorry
  planted.lean:9  theorem plain : 2 + 2 = 5 := sorry  -- expect: sorry
```

A static scan is a triage step. It says where to look and which lines need a human;
it can't prove the absence of tricks that only show up after elaboration. That is
what `#print axioms`, lean4checker and comparator in a sandbox are for.

## Statements

`statements` reads the modules a Lakefile lists as roots, prints every theorem with
its exact signature and unfolds statement definitions. It splits a statement into
binders, premises and conclusion, so `∀ (s : ℂ) (_ : riemannZeta s = 0) ...` and
`∀ s : ℂ, riemannZeta s = 0 → ...` line up item by item, and compares against
Mathlib's `RiemannHypothesis` (copied from `Mathlib/NumberTheory/LSeries/RiemannZeta.lean`
at the pinned commit). On the test project, a restatement that writes the cast
`(n : ℂ)` explicitly comes out as:

```
  against RiemannHypothesis (leanprover-community/mathlib4@0df444a360ea Mathlib/NumberTheory/LSeries/RiemannZeta.lean:185)
    binder     same
    premise    same
    premise    only here: `(`; only here: `: ℂ )`
      here:    ¬∃ n : ℕ, s = -2 * ((n : ℂ) + 1)
      mathlib: ¬∃ n : ℕ, s = -2 * (n + 1)
    premise    same
    conclusion same
```

It then searches the whole tree for declarations that reuse a name from the
statements and for `notation`, `syntax` or macros whose atoms mention one, which is
how a statement can be made to mean something other than what it says. The fixture
project plants both (`def riemannZeta` in a side namespace and
`notation "RiemannHypothesis" => True`), and the test checks that both are found.

## Declaration graph

`decls` builds a graph of declarations from source text alone. Each theorem, def,
structure and instance is a node, and an edge goes from a declaration to every
project name its signature or proof mentions. Names are resolved the way Lean would
look them up: the declaration's own namespaces from the innermost out (a
`theorem Foo.bar` inside `namespace A` sees `A.Foo`, `A` and the root), then the
file's `open`s, and a dotted name that matches nothing falls back to its prefix, so
`Pack.val` links to the structure `Pack`. It takes two passes over the files: the
first collects every declared name, the second resolves references against them,
which keeps memory to one integer per edge instead of holding a million proof bodies.

The walk starts from every declaration in the root modules. From the reached part it
computes the dominator tree (Cooper, Harvey and Kennedy's iterative algorithm): a
declaration dominates another if every chain of references from the main theorems to
the second passes through the first. Weighting each node by the source lines it
spans, the big subtrees are the lemmas the whole proof funnels through, which is a
more useful map of a large development than a raw call graph. On the fixture project:

```
dominator tree, subtrees of at least 1 lines, depth 8:
primitive  [2 decls, 7 lines]  src/Main.lean:8
  Proof.grh  [1 decls, 6 lines]  src/Proof/Core.lean:7
PrimitiveZerosOnLine  [1 decls, 3 lines]  src/Statements.lean:7
ZetaZerosOnLine  [1 decls, 3 lines]  src/Statements.lean:4
Proof.rh  [1 decls, 2 lines]  src/Proof/Core.lean:5
riemannHypothesis  [1 decls, 2 lines]  src/Main.lean:4
zeros  [1 decls, 2 lines]  src/Main.lean:6
```

`Proof.rh` sits at the top level because two main theorems use it, so neither
dominates it. `--svg` draws the same tree with a bar per node.

What a source-level graph misses is everything elaboration decides: instances found
by type class search, lemmas a `simp` set or a tactic picks up without naming them,
and generalized field notation (`h.trans` where only the type of `h` says which
`trans`). So "not reached by name" is not the same as unused. The exact graph needs
the built environment, which is the sandbox job's business.

## Manuscript triage

`manuscript` works on the page-numbered text from `pdftext`. It indexes numbered
results (`Theorem 7.2.1.4 (Title).`, nested parentheses in titles included) with
their pages, and builds a cross-reference graph by assigning each mention of a
numbered result to the result whose header precedes it. Mentions inside citation
brackets don't count, so `[AB, Lemma 1]` is not a reference to Lemma 1.
A line holding only `Theorem 3.1.2.4.` at the left margin is a sentence that wrapped,
not a header; the parser skips it.

It then reports references to numbers that have no header, numbers used by two
headers, gaps in each numbering sequence (and whether the missing number is an
equation label such as `(3.1.2.5)`, since equations share the counter), editorial
markers (`??` from unresolved LaTeX references, TODO, "to be written", omitted
proofs) with page and line, and every bracket citation matched against the
bibliography.

## Audit

`audit` runs the static checks above on one Lean project and writes a single report:
Lake configuration, the hatch scan, the statements of the root modules (the `roots` of
every `lean_lib` without globs, or `--module`), and the import cone of those modules.
Each finding has a severity (`critical`, `high`, `medium`, `low`, `info`), a code, a
file and line, and the text behind it. The JSON carries `"schema": 1` and is sorted,
so two runs over the same files give identical bytes. The exit code is 2 for any
critical finding, 1 for high, 0 otherwise, which makes it usable as a CI gate.

The import cone decides how much a hit matters. An `axiom` in a module the statement
files never import can't be in the proof, so it is reported as `low`; inside the cone
it stays `critical`. Low-risk hits inside the cone (raised heartbeats, notation) are
only counted, and so is any option set to `false` or `0`. On the root theorems it
looks at every hypothesis: `False`, `¬ True` or `⊥` is vacuous, a hypothesis equal to
the conclusion or naming the statement itself is circular, and a hypothesis that uses
a name the project declares gets flagged so a person reads that definition.

Names are checked against the module where the statement is elaborated, not the whole
project. If `Main` proves `ZerosOnLine` and that Prop is defined in a `Statements`
module that imports only Mathlib, then the `riemannZeta` inside it is Mathlib's, even
when `Main` imports a module that declares its own `riemannZeta`. Such a declaration
is reported as `low`. It becomes `high` only when the module declaring it is in the
import cone of the module where that name is read.

`debug.skipKernelTC` counts wherever it is set,
including `leanOptions` and `-D` arguments in the lakefile, where it would switch the
kernel off for a whole library without appearing in any `.lean` file.

On the fixture project (one `sorry` behind the RH theorem, and a shadowing definition
and notation in a module nothing imports):

```
$ zeta-checker audit tests/fixtures/project
project: leanprover/lean4:v4.33.1, lakefile.toml
7 modules, 41 lines; cone of Statements, Main
  3 modules, 29 lines
severity  findings
critical         2
high             0
medium           1
low              3
info             7
[critical] hatch sorry  src/Proof/Core.lean:5  theorem rh : RiemannHypothesis := sorry
[critical] hatch sorry  src/Proof/Core.lean:10  sorry
[medium] statement-differs  src/Main.lean:6  zeros vs RiemannHypothesis: premise: only here: `(`; only here: `: ℂ )`
```

`tests/test_audit.py` builds fake projects that each hide one trick and checks that
the audit flags it: a `False` hypothesis, `¬ True →`, RH assumed to prove RH, a
hypothesis defined in the project, an extra `axiom`, `skipKernelTC` in source, in
`leanOptions` and as a `-D` argument, `sorry` behind a macro, `native_decide`, a goal
closed with `MVarId.assign`, a project `riemannZeta`, notation over the statement's
name, the critical line moved to 1/3, no RH theorem at all, a `lakefile.lean`, a
module named like a Mathlib file, a manifest that disagrees with the pin and an
unofficial toolchain. A clean project is the control and must produce nothing at
`medium` or above.

## Tests

```
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

The tests never touch the network: downloads run against a fake server that drops
connections, ignores ranges and returns short bodies, and archives and PDFs are built
inside the tests.

## License

MIT
