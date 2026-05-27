from __future__ import annotations

import re
import unicodedata

try:
    from ftfy import fix_text as _ftfy_fix_text
except Exception:  # pragma: no cover - optional dependency
    _ftfy_fix_text = None


COMMON_ADMIN_REPLACEMENTS = {
    "ngäy": "ngày",
    "thäng": "tháng",
    "näm": "năm",
    "Ha Nói": "Hà Nội",
    "Ha Noi": "Hà Nội",
    "Hà Nói": "Hà Nội",
    "Ha Nội": "Hà Nội",
    "Hä Nội": "Hà Nội",
    "CONG HOA XA HOI CHU NGHIIA VIET NAM": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "CONG HOA XA HOI CHU NGHIA VIET NAM": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "DOC LAP - TU DO - HANH PHUC": "Độc lập - Tự do - Hạnh phúc",
    "VAN PHONG CHINH PHU": "VĂN PHÒNG CHÍNH PHỦ",
    "BO TRUONG": "BỘ TRƯỞNG",
    "PHO CHU NHIEM": "PHÓ CHỦ NHIỆM",
    "PHO THU TUONG": "PHÓ THỦ TƯỚNG",
    "THU TUONG": "THỦ TƯỚNG",
    "CHU NHIEM": "CHỦ NHIỆM",
    "CHINH PHU": "CHÍNH PHỦ",
    "BO XAY DUNG": "Bộ Xây dựng",
    "BO CONG THUONG": "Bộ Công Thương",
    "Noi nhận": "Nơi nhận",
    "Noi nhan": "Nơi nhận",
    "Như tren": "Như trên",
    "Nhu tren": "Như trên",
    "Chiên dịch": "Chiến dịch",
    "Chiến dich": "Chiến dịch",
    "Đông Khê": "Đông Khê",
    "Dong Khe": "Đông Khê",
    "Huu Nghi": "Hữu Nghị",
    "Chi Lang": "Chi Lăng",
    "Tra Linh": "Trà Lĩnh",
    "Cao Bang": "Cao Bằng",
    "Lang Son": "Lạng Sơn",
    "quyển han": "quyền hạn",
    "quyền han": "quyền hạn",
    "bỗ sung": "bổ sung",
    "bô sung": "bổ sung",
    "dé triển khai": "để triển khai",
    "de triển khai": "để triển khai",
    "an toan lao dong": "an toàn lao động",
}


COMMON_ADMIN_REGEX_REPLACEMENTS = [
    (r"\bVÀ\s+thành lập\b", "V/v thành lập"),
    (r"\bV[àa]\s+thành lập\b", "V/v thành lập"),
    (r"\bngay(?=\s+\d{1,2})", "ngày"),
    (r"\bthang(?=\s+\d{1,2})", "tháng"),
    (r"\bnam(?=\s+\d{4})", "năm"),
    (r"\bng[äa]y(?=\s+\d{1,2})", "ngày"),
    (r"\bth[äa]ng(?=\s+\d{1,2})", "tháng"),
    (r"\bn[äa]m(?=\s+\d{4})", "năm"),
    (r"\bS[óo0]\s*[:：]\s*", "Số: "),
    (r"\bK[ií]nh g[ưu]i\b", "Kính gửi"),
    (r"\bX[ée]t d[eề] ngh[ịi]\b", "Xét đề nghị"),
    (r"\bth[àa]nh l[ậa]p\b", "thành lập"),
    (r"\bQuy[eế]t d[ịi]nh\b", "Quyết định"),
    (r"\bd[ựu]\s+th[ảa]o\b", "dự thảo"),
    (r"\bTh[ủu]\s+t[ưu][ớo]ng\b", "Thủ tướng"),
    (r"\bB[ộo]\s+tr[ưu][ởo]ng\b", "Bộ trưởng"),
    (r"\bCh[ủu]\s+nhi[ệe]m\b", "Chủ nhiệm"),
    (r"\bPh[oó]\s+ch[ủu]\s+nhi[ệe]m\b", "Phó Chủ nhiệm"),
]


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
    for pattern, replacement in COMMON_ADMIN_REGEX_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def normalize_ocr_text(text: str) -> str:
    text = fix_mojibake(text or "")
    text = normalize_unicode(text)
    text = normalize_spacing(text)
    text = fix_common_admin_ocr_errors(text)
    return text


def normalize_lines(lines: list[str]) -> list[str]:
    return [line for line in (normalize_ocr_text(line) for line in lines) if line]


def layout_to_text(ocr_layout: dict) -> str:
    parts: list[str] = []
    for page in (ocr_layout or {}).get("pages") or []:
        lines = [normalize_ocr_text(str(line.get("text") or "")) for line in page.get("lines") or []]
        lines = [line for line in lines if line]
        if lines:
            parts.append("\n".join(lines))
    return normalize_ocr_text("\n\n".join(parts))
