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
