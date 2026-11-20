from __future__ import annotations

import io
import os
import re
import shutil
import tarfile
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from zeta_checker import fs

CHUNK = 1 << 20
RESERVED = {"con", "prn", "aux", "nul"} | {f"{d}{i}" for d in ("com", "lpt") for i in range(1, 10)}
BAD_CHARS = re.compile(r'[<>:"|?*\\\x00-\x1f]')


class UnsafeArchive(RuntimeError):
    pass


class Concat(io.RawIOBase):
    def __init__(self, paths: list[Path]):
        self._paths = list(paths)
        self._i = 0
        self._f = None

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        while self._i < len(self._paths):
            if self._f is None:
                self._f = open(self._paths[self._i], "rb")
            n = self._f.readinto(b)
            if n:
                return n
            self._f.close()
            self._f = None
            self._i += 1
        return 0

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None
        super().close()


def parts(folder: Path, stem: str) -> list[Path]:
    found = sorted(folder.glob(f"{stem}.part*"))
    found = [p for p in found if p.name[len(stem) + 5 :].isdigit()]
    if not found:
        raise FileNotFoundError(f"no {stem}.partNN files in {folder}")
    numbers = [int(p.name[len(stem) + 5 :]) for p in found]
    if numbers != list(range(1, len(found) + 1)):
        raise FileNotFoundError(f"{stem} parts are not numbered 1..{len(found)}: {numbers}")
    return found


def stream(paths: list[Path]) -> io.BufferedReader:
    return io.BufferedReader(Concat(paths), CHUNK)


def unsafe(m: tarfile.TarInfo) -> str | None:
    if m.issym():
        return "symlink"
    if m.islnk():
        return "hardlink"
    if m.ischr() or m.isblk():
        return "device"
    if m.isfifo():
        return "fifo"
    if not (m.isfile() or m.isdir()):
        return "special"
    name = m.name
    if not name or "\x00" in name:
        return "empty or nul name"
    if name.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", name):
        return "absolute"
    if ".." in re.split(r"[\\/]+", name):
        return "parent"
    return None


def unportable(name: str) -> str | None:
    for part in name.split("/"):
        if not part or part == ".":
            continue
        if BAD_CHARS.search(part):
            return "character"
        if part.split(".")[0].lower() in RESERVED:
            return "reserved"
        if part.endswith((" ", ".")):
            return "trailing"
    return None


@dataclass
class Listing:
    members: int = 0
    files: int = 0
    dirs: int = 0
    bytes: int = 0
    unsafe: list[tuple[str, str]] = field(default_factory=list)
    unportable: list[tuple[str, str]] = field(default_factory=list)
    collisions: list[tuple[str, str]] = field(default_factory=list)
    top: Counter = field(default_factory=Counter)

    @property
    def clean(self) -> bool:
        return not (self.unsafe or self.unportable or self.collisions)


def listing(fileobj) -> Listing:
    out = Listing()
    files: dict[str, str] = {}
    dirs: dict[str, str] = {}
    with tarfile.open(fileobj=fileobj, mode="r|*") as tf:
        for m in tf:
            out.members += 1
            reason = unsafe(m)
            if reason:
                out.unsafe.append((m.name, reason))
                continue
            name = m.name.strip("/")
            if why := unportable(name):
                out.unportable.append((name, why))
            pieces = [p for p in name.split("/") if p not in ("", ".")]
            for i in range(1, len(pieces) if m.isfile() else len(pieces) + 1):
                key = "/".join(pieces[:i]).lower()
                dirs.setdefault(key, "/".join(pieces[:i]))
            if m.isdir():
                out.dirs += 1
                continue
            out.files += 1
            out.bytes += m.size
            out.top[pieces[0] if len(pieces) == 1 else "/".join(pieces[:2])] += 1
            key = "/".join(pieces).lower()
            if key in files:
                out.collisions.append((files[key], name))
            else:
                files[key] = name
    for key, name in files.items():
        if key in dirs:
            out.collisions.append((name, dirs[key] + "/"))
    return out


def gzip_check(fileobj) -> tuple[int, int, int]:
    packed = unpacked = members = 0
    d = zlib.decompressobj(31)
    fed = False
    while block := fileobj.read(CHUNK):
        packed += len(block)
        while block:
            fed = True
            try:
                unpacked += len(d.decompress(block, 16 * CHUNK))
            except zlib.error as e:
                raise UnsafeArchive(f"bad gzip data after {members} members: {e}") from e
            if d.eof:
                members += 1
                block = d.unused_data
                d = zlib.decompressobj(31)
                fed = False
            else:
                block = d.unconsumed_tail
    if fed:
        raise UnsafeArchive("gzip stream ends inside a member")
    return packed, unpacked, members


def extract(paths: list[Path], dest: Path, *, reserve: int = 2 << 30) -> Listing:
    with stream(paths) as f:
        found = listing(f)
    if not found.clean:
        bad = found.unsafe[:5] + found.unportable[:5] + found.collisions[:5]
        raise UnsafeArchive(
            f"{len(found.unsafe)} unsafe, {len(found.unportable)} unportable and "
            f"{len(found.collisions)} colliding members, e.g. {bad}"
        )
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest).free
    if found.bytes + reserve > free:
        raise OSError(f"need {found.bytes} bytes plus {reserve} spare, only {free} free")
    base = os.path.abspath(dest)
    made = {base}
    with stream(paths) as f, tarfile.open(fileobj=f, mode="r|*") as tf:
        for m in tf:
            if unsafe(m):
                raise UnsafeArchive(f"{m.name} changed between passes")
            target = os.path.normpath(os.path.join(base, m.name.strip("/")))
            if not target.startswith(base + os.sep):
                raise UnsafeArchive(f"{m.name} resolves outside {base}")
            folder = target if m.isdir() else os.path.dirname(target)
            if folder not in made:
                os.makedirs(fs.long(folder), exist_ok=True)
                made.add(folder)
            if m.isdir():
                continue
            src = tf.extractfile(m)
            with open(fs.long(target), "xb") as out:
                shutil.copyfileobj(src, out, CHUNK)
    return found


def read_members(paths: list[Path], under: str = "", suffix: str = ""):
    prefix = under.strip("/") + "/" if under.strip("/") else ""
    with stream(paths) as f, tarfile.open(fileobj=f, mode="r|*") as tf:
        for m in tf:
            name = m.name[2:] if m.name.startswith("./") else m.name
            if m.isfile() and name.startswith(prefix) and name.endswith(suffix):
                yield name[len(prefix) :], tf.extractfile(m).read()


def count_lines(data: bytes) -> int:
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


@dataclass
class Inventory:
    files: int = 0
    lines: int = 0
    bytes: int = 0
    by_ext: dict[str, list[int]] = field(default_factory=dict)
    by_dir: dict[str, list[int]] = field(default_factory=dict)
    largest: list[tuple[int, str]] = field(default_factory=list)


def inventory(root: Path, depth: int = 2, top: int = 10) -> Inventory:
    base = fs.long(root)
    pairs = ((p.relative_to(base).as_posix(), p.read_bytes()) for p in fs.walk(root))
    return inventory_pairs(pairs, depth, top)


def inventory_pairs(pairs, depth: int = 2, top: int = 10) -> Inventory:
    inv = Inventory()
    sizes = []
    for rel, data in pairs:
        n = count_lines(data)
        name = rel.rsplit("/", 1)[-1]
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name.lstrip(".") else "(none)"
        key = "/".join(rel.split("/")[:depth]) if rel.count("/") >= depth else rel
        for table, k in ((inv.by_ext, ext), (inv.by_dir, key)):
            row = table.setdefault(k, [0, 0, 0])
            row[0] += 1
            row[1] += n
            row[2] += len(data)
        inv.files += 1
        inv.lines += n
        inv.bytes += len(data)
        sizes.append((n, rel))
    inv.largest = sorted(sizes, reverse=True)[:top]
    return inv
