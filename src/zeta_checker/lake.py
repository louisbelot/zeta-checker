from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from zeta_checker import fs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

OFFICIAL = re.compile(r"^leanprover/lean4:v\d+\.\d+\.\d+(?:-rc\d+)?$")
NATIVE_KEYS = {
    "precompileModules",
    "moreLinkArgs",
    "moreLinkObjs",
    "moreLinkLibs",
    "extern_lib",
    "lean_exe",
    "nativeFacets",
    "dynlibs",
    "plugins",
    "platformIndependent",
}
ARG_KEYS = {"moreLeanArgs", "weakLeanArgs", "moreServerArgs", "moreServerOptions", "leanOptions"}
CONFIG_FILES = {"lean-toolchain", "lakefile.toml", "lakefile.lean", "lake-manifest.json"}
MAGIC = {
    b"\x7fELF": "elf",
    b"MZ": "pe",
    b"\xcf\xfa\xed\xfe": "mach-o",
    b"\xca\xfe\xba\xbe": "mach-o",
    b"!<arch>": "static library",
    b"olean": "olean",
}


@dataclass
class Lake:
    root: Path
    toolchain: str | None
    lakefile: str | None
    config: dict
    manifest: dict
    notes: list[str] = field(default_factory=list)


def load(root: Path) -> Lake:
    tc = root / "lean-toolchain"
    toolchain = tc.read_text(encoding="utf-8").strip() if tc.exists() else None
    notes = []
    config, lakefile = {}, None
    if (root / "lakefile.toml").exists():
        lakefile = "lakefile.toml"
        config = tomllib.loads((root / lakefile).read_text(encoding="utf-8"))
    if (root / "lakefile.lean").exists():
        notes.append("lakefile.lean is Lean code that Lake runs when it loads the package")
        lakefile = lakefile or "lakefile.lean"
    if lakefile is None:
        notes.append("no lakefile")
    mf = root / "lake-manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    if toolchain is None:
        notes.append("no lean-toolchain file")
    elif not OFFICIAL.match(toolchain):
        notes.append(f"toolchain {toolchain!r} is not an official leanprover/lean4 release tag")
    return Lake(root, toolchain, lakefile, config, manifest, notes)


def pins(lake: Lake) -> list[dict]:
    packages = {p.get("name"): p for p in lake.manifest.get("packages", [])}
    out = []
    for req in lake.config.get("require", []):
        name = req.get("name")
        pkg = packages.get(name, {})
        wanted = req.get("rev") or req.get("version")
        out.append(
            {
                "name": name,
                "source": req.get("git") or req.get("scope") or req.get("path"),
                "lakefile": wanted,
                "manifest": pkg.get("rev"),
                "match": wanted is not None and wanted == pkg.get("rev"),
            }
        )
    return out


def packages(lake: Lake) -> list[dict]:
    keys = ("name", "url", "rev", "inputRev", "inherited", "type", "scope")
    return [{k: p.get(k) for k in keys} for p in lake.manifest.get("packages", [])]


def native(lake: Lake) -> list[str]:
    found = []

    def walk(obj, where):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in NATIVE_KEYS:
                    found.append(f"{where}{k} = {v!r}")
                walk(v, f"{where}{k}.")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{where}{i}.")

    walk(lake.config, "")
    return found


def arguments(lake: Lake) -> list[str]:
    rows = [f"{k} = {lake.config[k]!r}" for k in sorted(ARG_KEYS) if k in lake.config]
    for lib in lake.config.get("lean_lib", []):
        for k in sorted(ARG_KEYS):
            if k in lib:
                rows.append(f"lean_lib {lib.get('name')}: {k} = {lib[k]!r}")
    return rows


def _flat(opts: dict, prefix: str = "") -> list[tuple[str, object]]:
    out = []
    for k, v in opts.items():
        if isinstance(v, dict):
            out += _flat(v, f"{prefix}{k}.")
        else:
            out.append((f"{prefix}{k}", v))
    return out


_DARG = re.compile(r"^-D\s*([^=\s]+)=(.*)$")


def options(lake: Lake) -> list[tuple[str, str, str]]:
    scopes = [("package", lake.config)]
    scopes += [(f"lean_lib {lib.get('name')}", lib) for lib in lake.config.get("lean_lib", [])]
    out = []
    for where, cfg in scopes:
        out += [(where, k, str(v)) for k, v in _flat(cfg.get("leanOptions", {}))]
        for key in ("moreLeanArgs", "weakLeanArgs"):
            for arg in cfg.get(key, []):
                m = _DARG.match(str(arg))
                if m:
                    out.append((where, m.group(1), m.group(2)))
    return out


def roots(lake: Lake) -> list[str]:
    return [
        r
        for lib in lake.config.get("lean_lib", [])
        if "globs" not in lib
        for r in lib.get("roots", [])
    ]


def module_name(path: Path, src: Path) -> str:
    return ".".join(path.relative_to(src).with_suffix("").parts)


def glob_match(glob: str, module: str) -> bool:
    if glob.endswith(".+"):
        return module.startswith(glob[:-1])
    if glob.endswith(".*"):
        return module == glob[:-2] or module.startswith(glob[:-1])
    return module == glob


def lib_globs(lib: dict) -> list[str]:
    if "globs" in lib:
        return list(lib["globs"])
    return list(lib.get("roots", [lib.get("name")]))


def coverage(lake: Lake) -> dict:
    src = lake.root / lake.config.get("srcDir", ".")
    modules = sorted(module_name(p, fs.long(src)) for p in fs.walk(src, suffix=".lean"))
    libs = lake.config.get("lean_lib", [])
    default = set(lake.config.get("defaultTargets", []))
    per_lib = Counter()
    owners = Counter()
    orphans = []
    for mod in modules:
        hit = [lib["name"] for lib in libs if any(glob_match(g, mod) for g in lib_globs(lib))]
        for name in hit:
            per_lib[name] += 1
        owners[len(hit)] += 1
        if not hit:
            orphans.append(mod)
    return {
        "modules": len(modules),
        "per_lib": dict(per_lib),
        "not_default": sorted(
            n for n in (lib["name"] for lib in libs) if default and n not in default
        ),
        "unmatched": orphans,
        "multiple": sum(n for k, n in owners.items() if k > 1),
    }


def stray_files(root: Path) -> list[tuple[str, str]]:
    out = []
    base = fs.long(root)
    for path in fs.walk(root):
        rel = path.relative_to(base).as_posix()
        if path.suffix == ".lean" or rel in CONFIG_FILES:
            continue
        with path.open("rb") as f:
            head = f.read(8)
        kind = next((v for k, v in MAGIC.items() if head.startswith(k)), "other")
        out.append((rel, kind))
    return sorted(out)
