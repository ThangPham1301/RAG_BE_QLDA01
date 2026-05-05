"""Document parsing utilities (PDF extraction)."""
from __future__ import annotations

from typing import List

try:
    import fitz  # pymupdf
except Exception:  # pragma: no cover
    fitz = None


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF using PyMuPDF. Returns plain text.

    If PyMuPDF is not available, returns empty string.
    """
    if fitz is None:
        return ''
    doc = fitz.open(path)
    parts: List[str] = []
    for page in doc:
        text = page.get_text()
        if text:
            parts.append(text)
    return '\n\n'.join(parts)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Naive chunking by characters.

    Returns list of text chunks with overlap.
    """
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    L = len(text)
    while start < L:
        end = min(start + chunk_size, L)
        chunks.append(text[start:end])
        # Ensure we move forward; if end == L, we're done
        if end == L:
            break
        start = max(start + 1, end - overlap)  # Ensure forward progress
    return chunks
