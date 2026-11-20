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
in a throwaway Linux sandbox, not on a laptop. The kernel check will live in its own
CI job with no secrets.

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
```

`manifest.json` holds the URL, size, SHA-256 and the server's ETag and
Last-Modified for each of the 16 files. A rerun of `fetch` fails if a local file no
longer matches, and `fetch --upstream` flags a changed ETag or size on the server.
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
| unchecked | `opaque`, `unsafe`, `partial`, `unsafeCast` |
| meta | `macro`, `macro_rules`, `elab`, `syntax`, `notation`, `infix`, name literals like ``` ``sorryAx ``` |
| exec | `#eval`, `run_cmd`, `initialize`, `IO.Process` |
| options | every `set_option`, ranked by what the option can change |

Attribute names only count inside `@[...]` or `attribute [...]`, and an escaped
`«sorry»` is a plain identifier, reported separately. The tests plant every hatch in
`tests/fixtures/lean/planted.lean`, including a `sorry` inside a macro and one
inside an interpolated string, and put decoys in `decoys.lean`; each expected hit is
written next to its line, so the test is the file itself. Run on the fixtures:

```
$ zeta-checker scan tests/fixtures/lean --risk critical --show 1
2 files, 117 lines, 3732 bytes scanned
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
