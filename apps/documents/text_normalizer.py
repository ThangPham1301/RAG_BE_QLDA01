from __future__ import annotations

import re
import unicodedata

try:
    from ftfy import fix_text as _ftfy_fix_text
except Exception:  # pragma: no cover - optional dependency
    _ftfy_fix_text = None


COMMON_ADMIN_REPLACEMENTS = {
    "CONG HOA XA HOI CHU NGHIA VIET NAM": "CONG HOA XA HOI CHU NGHIA VIET NAM",
    "DOC LAP - TU DO - HANH PHUC": "DOC LAP - TU DO - HANH PHUC",
    "THU TUONG": "THU TUONG",
    "PHO THU TUONG": "PHO THU TUONG",
    "BO TRUONG": "BO TRUONG",
}


def fix_mojibake(text: str) -> str:
    if not text:
        return ""
    if _ftfy_fix_text:
        text = _ftfy_fix_text(text)
    return text


def normalize_unicode(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text)


def normalize_spacing(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    return text.strip()


def fix_common_admin_ocr_errors(text: str) -> str:
    if not text:
        return ""
    # Keep this conservative: only normalize exact repeated OCR artifacts.
    for wrong, right in COMMON_ADMIN_REPLACEMENTS.items():
        text = re.sub(re.escape(wrong), right, text, flags=re.IGNORECASE)
    return text


def normalize_ocr_text(text: str) -> str:
    text = fix_mojibake(text or "")
    text = normalize_unicode(text)
    text = normalize_spacing(text)
    text = fix_common_admin_ocr_errors(text)
    return text


def normalize_lines(lines: list[str]) -> list[str]:
    return [line for line in (normalize_ocr_text(line) for line in lines) if line]
