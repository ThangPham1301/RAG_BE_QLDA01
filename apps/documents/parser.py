"""Document parsing utilities (PDF extraction)."""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


def _get_fitz():
    """Import PyMuPDF lazily so a running server can pick up newly installed packages."""
    try:
        import fitz  # pymupdf
        return fitz
    except Exception as exc:  # pragma: no cover
        logger.warning(f'PyMuPDF (fitz) import failed: {exc}')
        return None


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF using PyMuPDF. Returns plain text.

    If PyMuPDF is not available, returns empty string.
    """
    logger.debug(f'[extract_text_from_pdf] Starting for {path}')
    fitz = _get_fitz()
    if fitz is None:
        logger.error('[extract_text_from_pdf] PyMuPDF not available')
        return ''
    
    try:
        doc = fitz.open(path)
        logger.debug(f'[extract_text_from_pdf] PDF opened, pages={len(doc)}')
    except Exception as e:
        logger.error(f'[extract_text_from_pdf] Failed to open PDF: {e}', exc_info=True)
        return ''
    
    parts: List[str] = []
    for idx, page in enumerate(doc):
        try:
            text = page.get_text("text") or page.get_text()
            if text:
                parts.append(text)
                logger.debug(f'[extract_text_from_pdf] Page {idx}: {len(text)} chars')
        except Exception as e:
            logger.warning(f'[extract_text_from_pdf] Failed to extract page {idx}: {e}')
    
    result = '\n\n'.join(parts)
    logger.debug(f'[extract_text_from_pdf] Total extracted: {len(result)} chars')
    return result


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


def extract_text_from_docx(path: str) -> str:
    """Extract text from a DOCX including paragraphs and tables."""
    try:
        from docx import Document as DocxDocument
    except Exception as exc:
        logger.error(f'[extract_text_from_docx] python-docx not available: {exc}')
        return ''

    try:
        doc = DocxDocument(path)
    except Exception as exc:
        logger.error(f'[extract_text_from_docx] Failed to open DOCX: {exc}', exc_info=True)
        return ''

    parts: List[str] = []

    for paragraph in doc.paragraphs:
        text = (paragraph.text or '').strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if row_text:
                parts.append(' | '.join(row_text))

    result = '\n'.join(parts)
    logger.debug(f'[extract_text_from_docx] Total extracted: {len(result)} chars')
    return result
