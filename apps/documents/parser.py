"""Document parsing utilities (PDF extraction)."""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)

try:
    import fitz  # pymupdf
    logger.info('PyMuPDF (fitz) successfully imported')
except Exception as e:  # pragma: no cover
    logger.warning(f'PyMuPDF (fitz) import failed: {e}')
    fitz = None


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF using PyMuPDF. Returns plain text.

    If PyMuPDF is not available, returns empty string.
    """
    logger.debug(f'[extract_text_from_pdf] Starting for {path}')
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
            text = page.get_text()
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
