from __future__ import annotations
from pathlib import Path

import pdfplumber


class NoTextLayer(Exception):
    """PDF has no extractable text — would need OCR."""


def extract_text(path: str | Path, max_pages: int = 3) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    chunks: list[str] = []
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages[:max_pages]:
            chunks.append(page.extract_text() or "")

    text = "\n".join(chunks).strip()
    if len(text) < 20:
        raise NoTextLayer(
            f"{p.name} has no usable text layer; an OCR stage would be required."
        )
    return text