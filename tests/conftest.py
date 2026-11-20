from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def tiny_pdf(texts: list[str], outline: list[tuple[str, int]] = ()) -> bytes:
    n = len(texts)
    pages = [4 + 2 * i for i in range(n)]
    contents = [5 + 2 * i for i in range(n)]
    root = 4 + 2 * n
    items = [root + 1 + i for i in range(len(outline))]
    objs = {
        1: "<< /Type /Catalog /Pages 2 0 R" + (f" /Outlines {root} 0 R" if outline else "") + " >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in pages)}] /Count {n} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(texts):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objs[pages[i]] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {contents[i]} 0 R >>"
        )
        objs[contents[i]] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    if outline:
        objs[root] = f"<< /Type /Outlines /First {items[0]} 0 R /Last {items[-1]} 0 R >>"
        for k, (title, page) in enumerate(outline):
            parts = [
                f"/Title ({title})",
                f"/Parent {root} 0 R",
                f"/Dest [{pages[page - 1]} 0 R /Fit]",
            ]
            if k:
                parts.append(f"/Prev {items[k - 1]} 0 R")
            if k < len(outline) - 1:
                parts.append(f"/Next {items[k + 1]} 0 R")
            objs[items[k]] = "<< " + " ".join(parts) + " >>"
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n{objs[num]}\nendobj\n".encode("latin-1")
    xref = len(out)
    size = max(objs) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for num in range(1, size):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
