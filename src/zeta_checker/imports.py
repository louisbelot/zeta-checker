from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

from zeta_checker import fs
from zeta_checker.archive import count_lines
from zeta_checker.leanlex import IDENT, mask

_IMPORT = re.compile(
    rf"^[ \t]*(?:(?:public|private)[ \t]+)?(?:meta[ \t]+)?import[ \t]+(?:all[ \t]+)?({IDENT})",
    re.M,
)
CORE = {"Init", "Lean", "Std", "Lake"}
LICENSE = re.compile(r"Released under Apache 2\.0 license|Copyright \(c\)")


@dataclass
class Graph:
    imports: dict[str, list[str]] = field(default_factory=dict)
    sizes: dict[str, tuple[int, int]] = field(default_factory=dict)
    headers: list[str] = field(default_factory=list)

    def external(self) -> Counter:
        roots = Counter()
        for deps in self.imports.values():
            for dep in deps:
                if dep not in self.imports:
                    roots[dep.split(".")[0]] += 1
        return roots

    def unresolved(self, packages: set[str]) -> list[tuple[str, str]]:
        known = packages | CORE
        return [
            (mod, dep)
            for mod, deps in self.imports.items()
            for dep in deps
            if dep not in self.imports and dep.split(".")[0] not in known
        ]

    def shadowing(self, packages: set[str]) -> list[str]:
        return sorted(m for m in self.imports if m.split(".")[0] in packages | CORE)

    def cone(self, roots: list[str]) -> set[str]:
        seen: set[str] = set()
        todo = deque(r for r in roots if r in self.imports)
        while todo:
            mod = todo.popleft()
            if mod in seen:
                continue
            seen.add(mod)
            todo.extend(d for d in self.imports[mod] if d in self.imports and d not in seen)
        return seen

    def totals(self, mods) -> tuple[int, int, int]:
        rows = [self.sizes[m] for m in mods]
        return len(rows), sum(r[0] for r in rows), sum(r[1] for r in rows)


def module_of(rel: str, src_dir: str = ".") -> str:
    prefix = "" if src_dir in (".", "") else src_dir.strip("/") + "/"
    rel = rel[len(prefix) :] if prefix and rel.startswith(prefix) else rel
    return rel.removesuffix(".lean").replace("/", ".")


def build(src: Path) -> Graph:
    g = Graph()
    base = fs.long(src)
    for path in fs.walk(src, suffix=".lean"):
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        mod = ".".join(path.relative_to(base).with_suffix("").parts)
        g.imports[mod] = _IMPORT.findall(mask(text).text)
        g.sizes[mod] = (count_lines(data), len(data))
        if LICENSE.search(text[:1000]):
            g.headers.append(mod)
    return g


def package_roots(manifest: dict) -> set[str]:
    known = {
        "mathlib": "Mathlib",
        "batteries": "Batteries",
        "aesop": "Aesop",
        "Qq": "Qq",
        "proofwidgets": "ProofWidgets",
        "plausible": "Plausible",
        "LeanSearchClient": "LeanSearchClient",
        "importGraph": "ImportGraph",
        "Cli": "Cli",
    }
    return {known.get(p["name"], p["name"]) for p in manifest.get("packages", [])}
