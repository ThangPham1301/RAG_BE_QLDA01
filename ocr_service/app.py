from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from paddleocr import PaddleOCR


app = FastAPI(title="RAG OCR Service", version="0.1.0")

_OCR_ENGINE: PaddleOCR | None = None


def get_ocr_engine() -> PaddleOCR:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        lang = os.getenv("PADDLE_OCR_LANG", "vi")
        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
    return _OCR_ENGINE


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _box_to_rect(box: Any) -> List[float]:
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return [min(xs), min(ys), max(xs), max(ys)]


def extract_image_layout(image_path: str) -> Dict[str, Any]:
    image = Image.open(image_path)
    width, height = image.size
    result = get_ocr_engine().ocr(image_path, cls=True)
    lines: List[Dict[str, Any]] = []

    for page_result in result or []:
        for item in page_result or []:
            if not item or len(item) < 2:
                continue
            box, payload = item[0], item[1]
            text = _normalize_text(payload[0] if payload else "")
            if not text:
                continue
            confidence = float(payload[1]) if payload and len(payload) > 1 else None
            lines.append(
                {
                    "text": text,
                    "bbox": _box_to_rect(box),
                    "confidence": confidence,
                }
            )

    lines.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    return {"pages": [{"page": 1, "width": width, "height": height, "lines": lines}]}


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr/image")
async def ocr_image(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = os.path.splitext(file.filename or "")[1].lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await file.read())

    try:
        return extract_image_layout(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
