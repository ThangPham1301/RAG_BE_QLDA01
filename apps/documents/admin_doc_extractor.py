from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List

from .text_normalizer import normalize_ocr_text


METADATA_KEYWORDS = [
    "nguoi ky:",
    "email:",
    "co quan:",
    "thoi gian ky:",
]

ORG_KEYWORDS = [
    "cong thong tin",
    "cong ttdt",
    "ttdt",
    "van phong",
    "chinh phu",
    "bo ",
    "uy ban",
    "ubnd",
]

SIGNING_TITLE_KEYWORDS = [
    "kt.",
    "tm.",
    "tl.",
    "tuq.",
    "thu tuong",
    "pho thu tuong",
    "bo truong",
    "chu nhiem",
    "pho chu nhiem",
    "chu tich",
    "giam doc",
]

RECIPIENT_CONTEXT_KEYWORDS = [
    "noi nhan",
    "luu:",
    "vpcp",
    "ttg",
    "pttg",
    "tgd",
    "tong gd",
    "tong giam doc",
    "ttdt",
    "ubnd",
    "cac vu",
    "cac cuc",
    "de b/c",
    "de phoi hop",
]


def _fold(text: str) -> str:
    text = normalize_ocr_text(text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d")


def _line_text(line: Dict[str, Any]) -> str:
    return normalize_ocr_text(str(line.get("text") or ""))


def _bbox(line: Dict[str, Any]) -> List[float]:
    box = line.get("bbox") or [0, 0, 0, 0]
    if len(box) != 4:
        return [0, 0, 0, 0]
    return [float(v or 0) for v in box]


def _line_center_y(line: Dict[str, Any]) -> float:
    _, y1, _, y2 = _bbox(line)
    return (y1 + y2) / 2


def _line_center_x(line: Dict[str, Any]) -> float:
    x1, _, x2, _ = _bbox(line)
    return (x1 + x2) / 2


def _is_metadata_line(text: str) -> bool:
    low = _fold(text)
    return any(keyword in low for keyword in METADATA_KEYWORDS)


def _has_org_word(text: str) -> bool:
    low = _fold(text)
    return any(keyword in low for keyword in ORG_KEYWORDS)


def _has_signing_title(text: str) -> bool:
    low = _fold(text)
    return any(keyword in low for keyword in SIGNING_TITLE_KEYWORDS)


def _has_signature_marker(text: str) -> bool:
    low = _fold(text)
    return any(keyword in low for keyword in ["kt.", "tm.", "tl.", "tuq."])


def _is_signature_title_anchor_line(text: str) -> bool:
    low = _fold(text)
    strong_keywords = [
        "kt.",
        "tm.",
        "tl.",
        "tuq.",
        "pho chu nhiem",
        "chu nhiem",
        "pho thu tuong",
        "bo truong",
        "chu tich",
        "giam doc",
    ]
    if not any(keyword in low for keyword in strong_keywords):
        return False

    stripped = low.strip()
    is_list_item = stripped.startswith("-") or stripped.startswith("+")
    if is_list_item:
        return False

    # "Noi nhan: KT. ..." is a common OCR merge of two columns; keep it only
    # when the line contains an explicit signing marker.
    if _is_recipient_context_line(text) and not _has_signature_marker(text):
        return False
    return True


def _is_recipient_context_line(text: str) -> bool:
    low = _fold(text).strip()
    if not low:
        return False
    if low.startswith("-") or low.startswith("+"):
        return True
    return any(keyword in low for keyword in RECIPIENT_CONTEXT_KEYWORDS)


def _has_recipient_context(lines: List[Dict[str, Any]]) -> bool:
    return any(_is_recipient_context_line(_line_text(line)) for line in lines)


def _find_signature_title_anchors(page_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    anchors = []
    for line in page_lines:
        text = _line_text(line)
        if _is_signature_title_anchor_line(text):
            anchors.append(line)
    return anchors


def _signature_anchor_for_candidate(
    candidate_line: Dict[str, Any],
    anchors: List[Dict[str, Any]],
    page_width: float,
    page_height: float,
) -> Dict[str, Any] | None:
    if not anchors:
        return None

    candidate_x = _line_center_x(candidate_line)
    candidate_y = _line_center_y(candidate_line)
    best = None
    best_score = -1.0

    for anchor in anchors:
        anchor_x = _line_center_x(anchor)
        anchor_y = _line_center_y(anchor)
        if anchor_y >= candidate_y:
            continue

        vertical_gap = candidate_y - anchor_y
        max_gap = page_height * 0.35 if page_height else 350
        if vertical_gap > max_gap:
            continue

        # Signature blocks are usually right side; tolerate slightly centered scans.
        if page_width and candidate_x < page_width * 0.42 and anchor_x < page_width * 0.42:
            continue

        horizontal_distance = abs(candidate_x - anchor_x)
        score = max_gap - vertical_gap
        if page_width:
            score += max(0, page_width * 0.35 - horizontal_distance)
        if score > best_score:
            best = anchor
            best_score = score

    return best


def _looks_like_person_name(text: str) -> bool:
    original_text = normalize_ocr_text(text)
    text = original_text.strip(" :-,.;\"'“”‘’()[]{}")
    if not text or len(text) > 60:
        return False
    if original_text.rstrip().endswith((",", ";", ":")):
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if _is_metadata_line(text) or _has_signing_title(text) or _has_org_word(text) or _is_recipient_context_line(text):
        return False

    words = [word for word in re.split(r"\s+", text) if word]
    if not 2 <= len(words) <= 5:
        return False

    short_words = {"va", "và", "de", "để", "noi", "nơi", "nhu", "như", "tren", "trên"}
    if any(word.lower() in short_words for word in words):
        return False
    if any(word.isupper() and len(word) <= 5 for word in words):
        return False

    return all(re.match(r"^[A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ'.-]+$", word) for word in words)


def _flatten_layout_lines(ocr_layout: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for page in ocr_layout.get("pages") or []:
        page_no = page.get("page") or 1
        width = float(page.get("width") or 0)
        height = float(page.get("height") or 0)
        for raw_line in page.get("lines") or []:
            text = _line_text(raw_line)
            if not text:
                continue
            item = dict(raw_line)
            item["text"] = text
            item["page"] = page_no
            item["page_width"] = width
            item["page_height"] = height
            lines.append(item)
    return sorted(lines, key=lambda item: (item.get("page") or 1, _line_center_y(item), _line_center_x(item)))


def _plain_text_lines(plain_text: str) -> List[Dict[str, Any]]:
    return [
        {
            "text": normalize_ocr_text(line),
            "page": 1,
            "bbox": [0, index * 20, 0, index * 20 + 10],
            "confidence": None,
        }
        for index, line in enumerate((plain_text or "").splitlines())
        if normalize_ocr_text(line)
    ]


def _extract_signer_from_text_block(plain_text: str) -> Dict[str, Any] | None:
    lines = [normalize_ocr_text(line) for line in (plain_text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    # Work from the end of the document: signature blocks are normally after the body.
    tail = lines[-40:]
    title_indexes = [index for index, line in enumerate(tail) if _is_signature_title_anchor_line(line)]
    if not title_indexes:
        return None

    best = None
    for title_index in title_indexes:
        # OCR can interleave the left "Noi nhan" column between the signing title
        # and the handwritten/signature name, so keep a wider but still tail-only window.
        window = tail[title_index + 1:title_index + 30]
        title_evidence = [
            line
            for line in tail[max(0, title_index - 1):title_index + 3]
            if _is_signature_title_anchor_line(line) and not _has_org_word(line)
        ]
        for line in window:
            if _is_recipient_context_line(line) or _is_metadata_line(line) or _has_org_word(line):
                continue
            if not _looks_like_person_name(line):
                continue
            best = {
                "value": line.strip(" :-,.;\"'“”‘’()[]{}"),
                "confidence": 0.82,
                "evidence": title_evidence + [line],
                "source": "signature_text_block",
                "status": "found",
                "alternatives": [],
            }
    return best


def extract_digital_signature_metadata(lines: List[Dict[str, Any]]) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for line in lines[:20]:
        text = _line_text(line)
        low = _fold(text)
        if "nguoi ky:" in low:
            metadata["nguoi_ky_raw"] = text.split(":", 1)[-1].strip()
        elif low.startswith("email:"):
            metadata["email"] = text.split(":", 1)[-1].strip()
        elif "co quan:" in low:
            metadata["co_quan"] = text.split(":", 1)[-1].strip()
        elif "thoi gian ky:" in low:
            metadata["thoi_gian_ky"] = text.split(":", 1)[-1].strip()
    return metadata


def extract_document_number(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    def find_number(text: str) -> str | None:
        patterns = [
            r"S[ốo0óòõỏọ]\s*[:：]?\s*([0-9O]{2,6}/[A-ZĐA-Z0-9.-]+)",
            r"\b([0-9O]{2,6}/[A-ZĐA-Z0-9.-]*(?:VPCP|UBND|QĐ|QD|CV|CN|BXD|BCT)[A-ZĐA-Z0-9.-]*)\b",
            r"\b([0-9O]{2,6}/[A-ZĐA-Z]{2,}[A-ZĐA-Z0-9.-]*)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).replace("O", "0").strip(" .,;:")
        return None

    for index, line in enumerate(lines[:30]):
        text = _line_text(line)
        folded = _fold(text)
        has_number_anchor = "so:" in folded or folded.startswith("so ") or folded.startswith("s0") or folded.startswith("s6")
        value = find_number(text)
        if not value and index + 1 < len(lines):
            value = find_number(f"{text} {_line_text(lines[index + 1])}")

        if value and (has_number_anchor or index < 15):
            return {
                "value": value,
                "confidence": 0.95,
                "evidence": f"Số: {value}",
                "status": "found",
            }

    all_header_text = " ".join(_line_text(line) for line in lines[:30])
    value = find_number(all_header_text)
    if value:
        return {
            "value": value,
            "confidence": 0.8,
            "evidence": f"Số: {value}",
            "status": "found",
        }

    return {"value": None, "confidence": 0.0, "status": "not_found", "evidence": ""}


def extract_place_date(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    for line in lines[:40]:
        text = _line_text(line)
        folded = _fold(text)
        if "ngay" not in folded or "thang" not in folded or "nam" not in folded:
            continue

        location_match = re.search(
            r"((?:Hà Nội|Ha Noi|TP\.?\s*Hồ Chí Minh|Thành phố Hồ Chí Minh|Đà Nẵng|Da Nang),\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
            text,
            flags=re.IGNORECASE,
        )
        match = location_match or re.search(
            r"([A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ .-]{1,40}?,\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            # If OCR merged "Số: 1744/VPCP-CN" before the date, keep only the place/date suffix.
            suffix_match = re.search(
                r"([A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ .-]{1,25}?,\s*ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})$",
                match.group(1).strip(),
                flags=re.IGNORECASE,
            )
            if suffix_match:
                match = suffix_match
        value = match.group(1).strip(" .,;:") if match else text.strip(" .,;:")
        return {
            "value": value,
            "confidence": 0.9,
            "evidence": value,
            "status": "found",
        }

    return {"value": None, "confidence": 0.0, "status": "not_found", "evidence": ""}


def extract_signer(ocr_layout: Dict[str, Any], plain_text: str = "") -> Dict[str, Any]:
    lines = _flatten_layout_lines(ocr_layout)
    if not lines:
        lines = _plain_text_lines(plain_text)
    if not lines:
        return {"value": None, "confidence": 0.0, "status": "not_found", "evidence": []}

    last_page = max(int(line.get("page") or 1) for line in lines)
    page_lines = [line for line in lines if int(line.get("page") or 1) == last_page]
    page_height = max((float(line.get("page_height") or 0) for line in page_lines), default=0)
    page_width = max((float(line.get("page_width") or 0) for line in page_lines), default=0)
    signature_anchors = _find_signature_title_anchors(page_lines)

    candidates = []
    for index, line in enumerate(page_lines):
        text = _line_text(line)
        if not _looks_like_person_name(text):
            continue

        y = _line_center_y(line)
        x = _line_center_x(line)
        nearby_before = page_lines[max(0, index - 6):index]
        context_lines = nearby_before + [line]
        title_lines = [_line_text(item) for item in nearby_before if _is_signature_title_anchor_line(_line_text(item))]
        anchor = _signature_anchor_for_candidate(line, signature_anchors, page_width, page_height)
        if anchor and _line_text(anchor) not in title_lines:
            title_lines.append(_line_text(anchor))
        has_title = bool(title_lines)
        in_recipient_context = _has_recipient_context(context_lines)
        in_lower_page = bool(page_height and y >= page_height * 0.55)
        in_right_signature_area = bool(page_width and page_height and x >= page_width * 0.48 and y >= page_height * 0.50)

        # A name in the left-side "Noi nhan" block is not a signer unless a signing title is nearby.
        if in_recipient_context and not has_title:
            continue
        # Avoid accepting arbitrary names from the body: require title evidence or the right-side signature area.
        if not has_title and not in_right_signature_area:
            continue

        evidence_lines = [
            _line_text(item)
            for item in nearby_before[-5:]
            if (
                _is_signature_title_anchor_line(_line_text(item))
                and not _is_metadata_line(_line_text(item))
                and not _is_recipient_context_line(_line_text(item))
                and not _has_org_word(_line_text(item))
                and (not page_width or _line_center_x(item) >= page_width * 0.42)
            )
        ] + [text]
        if anchor:
            anchor_text = _line_text(anchor)
            evidence_lines = [anchor_text] + [item for item in evidence_lines if item != anchor_text]

        score = 35
        if in_lower_page:
            score += 20
        if in_right_signature_area:
            score += 25
        if has_title:
            score += 45

        confidence = line.get("confidence")
        if isinstance(confidence, (int, float)):
            score += min(max(float(confidence), 0.0), 1.0) * 10
        if _is_metadata_line(text) or _has_org_word(text):
            score -= 80

        candidates.append(
            {
                "value": text,
                "score": score,
                "confidence": round(min(score / 100, 0.99), 2),
                "evidence": [item for item in evidence_lines if item],
                "source": "signature_region" if has_title else "right_signature_area",
            }
        )

    if not candidates:
        fallback = _extract_signer_from_text_block(plain_text)
        if fallback:
            return fallback
        layout_text = "\n".join(_line_text(line) for line in page_lines)
        fallback = _extract_signer_from_text_block(layout_text)
        if fallback:
            return fallback
        return {"value": None, "confidence": 0.0, "status": "not_found", "evidence": []}

    best = max(candidates, key=lambda item: item["score"])
    if best["score"] < 70:
        fallback = _extract_signer_from_text_block(plain_text)
        if fallback:
            return fallback
        layout_text = "\n".join(_line_text(line) for line in page_lines)
        fallback = _extract_signer_from_text_block(layout_text)
        if fallback:
            return fallback
        return {
            "value": None,
            "confidence": best["confidence"],
            "status": "uncertain",
            "evidence": best["evidence"],
            "alternatives": sorted(candidates, key=lambda item: item["score"], reverse=True)[:5],
        }

    best["status"] = "found"
    best["alternatives"] = sorted(candidates, key=lambda item: item["score"], reverse=True)[1:5]
    best.pop("score", None)
    return best


def extract_administrative_fields(ocr_layout: Dict[str, Any], plain_text: str = "") -> Dict[str, Any]:
    lines = _flatten_layout_lines(ocr_layout)
    if not lines:
        lines = _plain_text_lines(plain_text)
    return {
        "digital_signature_metadata": extract_digital_signature_metadata(lines),
        "document_number": extract_document_number(lines),
        "place_date": extract_place_date(lines),
        "signer": extract_signer(ocr_layout, plain_text=plain_text),
    }
