import shutil

import pytest
from conftest import tiny_pdf

from zeta_checker import pdftext


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "note.pdf"
    texts = ["Introduction to the zeta function", "Main Theorem holds", "Appendix on sorry"]
    outline = [("Introduction", 1), ("Proof", 2), ("Appendix", 3)]
    path.write_bytes(tiny_pdf(texts, outline))
    return path


def test_pypdf_pages_and_outline(pdf):
    doc = pdftext.read(pdf, "pypdf")
    assert doc.engine == "pypdf" and doc.meta["pages"] == 3
    assert "Main Theorem" in doc.pages[1]
    assert doc.outline == [(0, "Introduction", 1), (0, "Proof", 2), (0, "Appendix", 3)]


def test_render_and_find(pdf, tmp_path):
    doc = pdftext.read(pdf, "pypdf")
    text, outline = pdftext.write(doc, tmp_path / "out", "note")
    body = text.read_text(encoding="utf-8")
    assert body.startswith("--- page 1 ---\n")
    assert body.count("--- page ") == 3
    assert outline.read_text(encoding="utf-8").splitlines()[1] == "Proof  ..  2"
    hits = pdftext.find(body, r"theorem|sorry")
    assert [(p, line) for p, line, _ in hits] == [(2, 1), (3, 1)]


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_pdftotext_engine(pdf):
    doc = pdftext.read(pdf, "pdftotext")
    assert doc.engine == "pdftotext"
    assert len(doc.pages) == 3 and "Appendix" in doc.pages[2]
