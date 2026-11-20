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
