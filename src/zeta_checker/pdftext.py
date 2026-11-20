from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

MARK = re.compile(r"^--- page (\d+) ---$", re.M)


@dataclass
class Document:
    pages: list[str]
    outline: list[tuple[int, str, int | None]]
    meta: dict
    engine: str


def _outline(reader: PdfReader, items, level: int = 0):
    for item in items:
        if isinstance(item, list):
            yield from _outline(reader, item, level + 1)
            continue
        try:
            page = reader.get_destination_page_number(item) + 1
        except (KeyError, ValueError, TypeError):
            page = None
        yield level, str(item.title), page


def _pdftotext(pdf: Path, exe: str) -> list[str]:
    run = subprocess.run(
        [exe, "-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        check=True,
        timeout=600,
    )
    pages = run.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def read(pdf: Path, engine: str = "auto") -> Document:
    reader = PdfReader(pdf)
    exe = shutil.which("pdftotext") if engine in ("auto", "pdftotext") else None
    if engine == "pdftotext" and exe is None:
        raise FileNotFoundError("pdftotext is not on PATH")
    if exe:
        pages, used = _pdftotext(pdf, exe), "pdftotext"
    else:
        pages, used = [p.extract_text() or "" for p in reader.pages], "pypdf"
    info = reader.metadata or {}
    meta = {k.lstrip("/"): str(v) for k, v in info.items()}
    meta["pages"] = len(reader.pages)
    if len(pages) != len(reader.pages):
        raise ValueError(f"{used} gave {len(pages)} pages, the file has {len(reader.pages)}")
    return Document(pages, list(_outline(reader, reader.outline)), meta, used)


def render(doc: Document) -> str:
    out = []
    for i, text in enumerate(doc.pages, 1):
        out.append(f"--- page {i} ---")
        out.append(text.rstrip())
    return "\n".join(out) + "\n"


def render_outline(doc: Document) -> str:
    rows = [f"{'  ' * level}{title}  ..  {page or '?'}" for level, title, page in doc.outline]
    return "\n".join(rows) + ("\n" if rows else "")


def write(doc: Document, out: Path, stem: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    text = out / f"{stem}.txt"
    outline = out / f"{stem}.outline.txt"
    text.write_text(render(doc), encoding="utf-8")
    outline.write_text(render_outline(doc), encoding="utf-8")
    return [text, outline]


def find(text: str, pattern: str, flags: int = re.I) -> list[tuple[int, int, str]]:
    rx = re.compile(pattern, flags)
    page, line_in_page, hits = 0, 0, []
    for line in text.splitlines():
        m = MARK.match(line)
        if m:
            page, line_in_page = int(m.group(1)), 0
            continue
        line_in_page += 1
        if rx.search(line):
            hits.append((page, line_in_page, line.strip()))
    return hits
