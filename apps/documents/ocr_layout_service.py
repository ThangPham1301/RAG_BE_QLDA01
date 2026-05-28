from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Dict, List

import requests
from decouple import config

from .text_normalizer import normalize_ocr_text

logger = logging.getLogger(__name__)


class OCRLayoutService:
    """Extract OCR text lines with page coordinates.

    PaddleOCR is preferred when installed. Tesseract is used as a fallback
    because this project already supports it for OCR.
    """

    def __init__(self):
        self._paddle = None
        self._tesseract_ready = False

    def _get_paddle(self):
        if self._paddle is not None:
            return self._paddle
        try:
            from paddleocr import PaddleOCR

            lang = config("PADDLE_OCR_LANG", default="vi")
            self._paddle = PaddleOCR(use_angle_cls=True, lang=lang)
            return self._paddle
        except Exception as exc:
            logger.info("[OCRLayoutService] PaddleOCR unavailable: %s", exc)
            return None

    def _ensure_tesseract(self) -> bool:
        if self._tesseract_ready:
            return True
        try:
            import pytesseract

            tesseract_cmd = config("TESSERACT_CMD", default=r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._tesseract_ready = True
            return True
        except Exception as exc:
            logger.info("[OCRLayoutService] Tesseract unavailable: %s", exc)
            return False

    def extract_pdf_layout(self, pdf_path: str) -> Dict[str, Any]:
        try:
            import fitz
        except Exception as exc:
            logger.warning("[OCRLayoutService] PyMuPDF unavailable: %s", exc)
            return {"pages": []}

        pages = []
        dpi = int(config("OCR_RENDER_DPI", default=200))
        zoom = dpi / 72

        try:
            doc = fitz.open(pdf_path)
            for page_index, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    pix.save(tmp_path)
                    page_layout = self.extract_image_layout(tmp_path, include_signature_crop=False)
                    lines = (page_layout.get("pages") or [{}])[0].get("lines") or []
                    lines = self._merge_lines(
                        lines,
                        self._extract_signature_crop_lines(tmp_path, pix.width, pix.height),
                    )
                    pages.append(
                        {
                            "page": page_index + 1,
                            "width": pix.width,
                            "height": pix.height,
                            "lines": lines,
                        }
                    )
                finally:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except Exception as exc:
            logger.warning("[OCRLayoutService] PDF layout extraction failed: %s", exc, exc_info=True)
            return {"pages": pages}
        return {"pages": pages}

    def extract_image_layout(self, image_path: str, include_signature_crop: bool = True) -> Dict[str, Any]:
        remote_layout = self._extract_with_remote_service(image_path)
        if remote_layout is not None:
            if include_signature_crop:
                remote_layout = self._append_signature_crop(image_path, remote_layout)
            return remote_layout

        paddle = self._get_paddle()
        if paddle:
            try:
                layout = self._extract_with_paddle(paddle, image_path)
                if include_signature_crop:
                    layout = self._append_signature_crop(image_path, layout)
                return layout
            except Exception as exc:
                logger.warning("[OCRLayoutService] PaddleOCR failed, fallback to Tesseract: %s", exc)

        if self._ensure_tesseract():
            layout = self._extract_with_tesseract(image_path)
            if include_signature_crop:
                layout = self._append_signature_crop(image_path, layout)
            return layout
        return {"pages": []}

    def _append_signature_crop(self, image_path: str, layout: Dict[str, Any]) -> Dict[str, Any]:
        pages = (layout or {}).get("pages") or []
        if not pages:
            return layout
        page = pages[0]
        width = int(page.get("width") or 0)
        height = int(page.get("height") or 0)
        if not width or not height:
            return layout
        page["lines"] = self._merge_lines(
            page.get("lines") or [],
            self._extract_signature_crop_lines(image_path, width, height),
        )
        return {"pages": pages}

    def _extract_signature_crop_lines(self, image_path: str, width: int, height: int) -> List[Dict[str, Any]]:
        if not config("OCR_SIGNATURE_CROP_ENABLED", default=True, cast=bool):
            return []

        try:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        except Exception as exc:
            logger.info("[OCRLayoutService] PIL unavailable for signature crop: %s", exc)
            return []

        # Administrative signatures are usually at the lower-right area. The
        # crop also includes a little center-left because seals can shift the name.
        crop_box = (
            int(width * 0.32),
            int(height * 0.50),
            width,
            height,
        )
        scale = float(config("OCR_SIGNATURE_CROP_SCALE", default=2.0, cast=float))

        try:
            image = Image.open(image_path).convert("RGB")
            crop = image.crop(crop_box)
            if scale > 1:
                crop = crop.resize((int(crop.width * scale), int(crop.height * scale)))
            crop = ImageOps.grayscale(crop)
            crop = ImageOps.autocontrast(crop)
            crop = ImageEnhance.Contrast(crop).enhance(1.6)
            crop = crop.filter(ImageFilter.SHARPEN)

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                crop_path = tmp.name
            try:
                crop.save(crop_path)
                crop_layout = self.extract_image_layout(crop_path, include_signature_crop=False)
            finally:
                try:
                    os.remove(crop_path)
                except OSError:
                    pass
        except Exception as exc:
            logger.info("[OCRLayoutService] Signature crop OCR failed: %s", exc)
            return []

        lines = []
        offset_x, offset_y = crop_box[0], crop_box[1]
        for page in (crop_layout or {}).get("pages") or []:
            for line in page.get("lines") or []:
                bbox = line.get("bbox") or [0, 0, 0, 0]
                if len(bbox) != 4:
                    continue
                remapped = [
                    float(bbox[0]) / scale + offset_x,
                    float(bbox[1]) / scale + offset_y,
                    float(bbox[2]) / scale + offset_x,
                    float(bbox[3]) / scale + offset_y,
                ]
                text = normalize_ocr_text(str(line.get("text") or ""))
                if text:
                    lines.append(
                        {
                            "text": text,
                            "bbox": remapped,
                            "confidence": line.get("confidence"),
                            "source": "signature_crop",
                        }
                    )
        return lines

    def _merge_lines(self, base_lines: List[Dict[str, Any]], extra_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = list(base_lines or [])
        for extra in extra_lines or []:
            extra_text = normalize_ocr_text(str(extra.get("text") or ""))
            extra_box = extra.get("bbox") or [0, 0, 0, 0]
            duplicate = False
            for current in merged:
                current_text = normalize_ocr_text(str(current.get("text") or ""))
                current_box = current.get("bbox") or [0, 0, 0, 0]
                if extra_text == current_text and len(current_box) == 4:
                    if abs(float(extra_box[1]) - float(current_box[1])) < 30:
                        duplicate = True
                        break
            if not duplicate:
                merged.append(extra)
        return sorted(merged, key=lambda item: ((item.get("bbox") or [0, 0, 0, 0])[1], (item.get("bbox") or [0, 0, 0, 0])[0]))

    def _extract_with_remote_service(self, image_path: str) -> Dict[str, Any] | None:
        use_remote = config("OCR_USE_REMOTE", default=True, cast=bool)
        if not use_remote:
            return None

        url = config("OCR_REMOTE_URL", default="http://127.0.0.1:8100/ocr/image")
        timeout = config("OCR_REMOTE_TIMEOUT", default=30, cast=int)
        try:
            with open(image_path, "rb") as handle:
                response = requests.post(
                    url,
                    files={"file": (os.path.basename(image_path), handle, "image/png")},
                    timeout=timeout,
                )
            response.raise_for_status()
            layout = response.json()
            return self._normalize_layout(layout)
        except Exception as exc:
            logger.info("[OCRLayoutService] Remote OCR unavailable, fallback locally: %s", exc)
            return None

    def _normalize_layout(self, layout: Dict[str, Any]) -> Dict[str, Any]:
        pages = []
        for page in (layout or {}).get("pages") or []:
            lines = []
            for line in page.get("lines") or []:
                text = normalize_ocr_text(str(line.get("text") or ""))
                if not text:
                    continue
                item = {
                    "text": text,
                    "bbox": line.get("bbox") or [0, 0, 0, 0],
                    "confidence": line.get("confidence"),
                }
                for key in ["recognizer", "paddle_text", "source"]:
                    if line.get(key):
                        item[key] = line.get(key)
                lines.append(item)
            pages.append(
                {
                    "page": page.get("page") or len(pages) + 1,
                    "width": page.get("width") or 0,
                    "height": page.get("height") or 0,
                    "lines": lines,
                }
            )
        return {"pages": pages}

    def _extract_with_paddle(self, paddle, image_path: str) -> Dict[str, Any]:
        from PIL import Image

        image = Image.open(image_path)
        width, height = image.size
        result = paddle.ocr(image_path, cls=True)
        lines: List[Dict[str, Any]] = []

        for page_result in result or []:
            for item in page_result or []:
                if not item or len(item) < 2:
                    continue
                box, payload = item[0], item[1]
                text = normalize_ocr_text(payload[0] if payload else "")
                confidence = float(payload[1]) if payload and len(payload) > 1 else None
                if not text:
                    continue
                xs = [float(point[0]) for point in box]
                ys = [float(point[1]) for point in box]
                lines.append(
                    {
                        "text": text,
                        "bbox": [min(xs), min(ys), max(xs), max(ys)],
                        "confidence": confidence,
                    }
                )
        return {"pages": [{"page": 1, "width": width, "height": height, "lines": lines}]}

    def _extract_with_tesseract(self, image_path: str) -> Dict[str, Any]:
        from PIL import Image
        import pytesseract
        from pytesseract import Output

        image = Image.open(image_path)
        width, height = image.size
        lang = config("OCR_LANGUAGE", default="vie+eng")
        data = pytesseract.image_to_data(image, lang=lang, output_type=Output.DICT)

        grouped: Dict[tuple, List[int]] = {}
        for idx, text in enumerate(data.get("text") or []):
            if not normalize_ocr_text(text):
                continue
            key = (
                data["block_num"][idx],
                data["par_num"][idx],
                data["line_num"][idx],
            )
            grouped.setdefault(key, []).append(idx)

        lines = []
        for indexes in grouped.values():
            words = [normalize_ocr_text(data["text"][idx]) for idx in indexes]
            text = normalize_ocr_text(" ".join(word for word in words if word))
            if not text:
                continue
            left = min(data["left"][idx] for idx in indexes)
            top = min(data["top"][idx] for idx in indexes)
            right = max(data["left"][idx] + data["width"][idx] for idx in indexes)
            bottom = max(data["top"][idx] + data["height"][idx] for idx in indexes)
            confs = []
            for idx in indexes:
                try:
                    confs.append(float(data["conf"][idx]) / 100)
                except Exception:
                    pass
            confidence = sum(confs) / len(confs) if confs else None
            lines.append({"text": text, "bbox": [left, top, right, bottom], "confidence": confidence})

        lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        return {"pages": [{"page": 1, "width": width, "height": height, "lines": lines}]}
