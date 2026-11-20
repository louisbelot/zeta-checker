from __future__ import annotations

import os
from pathlib import Path

PREFIX = "\\\\?\\"


def long(path: Path | str) -> Path:
    if os.name != "nt":
        return Path(path)
    s = os.path.abspath(path)
    return Path(s if s.startswith(PREFIX) else PREFIX + s)


def short(path: Path | str) -> str:
    s = str(path)
    return s[len(PREFIX) :] if s.startswith(PREFIX) else s


def walk(root: Path, skip: set[str] = frozenset(), suffix: str = ""):
    def fail(err: OSError):
        raise err

    for folder, dirs, files in os.walk(long(root), onerror=fail):
        dirs[:] = sorted(d for d in dirs if d not in skip)
        for f in sorted(files):
            if f.endswith(suffix):
                yield Path(folder) / f
