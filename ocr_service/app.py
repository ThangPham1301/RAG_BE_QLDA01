from __future__ import annotations

import os
import tempfile
import time
from typing import Any, Dict, List

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image


app = FastAPI(title="RAG OCR Service", version="0.2.0")

_OCR_ENGINE = None
_VIETOCR_PREDICTOR = None
_VIETOCR_ERROR = ""
_PADDLE_ERROR = ""


def get_ocr_engine():
    global _OCR_ENGINE, _PADDLE_ERROR
    if _OCR_ENGINE is None:
        try:
            from paddleocr import PaddleOCR

            lang = os.getenv("PADDLE_OCR_LANG", "vi")
            _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
            _PADDLE_ERROR = ""
        except Exception as exc:
            _PADDLE_ERROR = f"{type(exc).__name__}: {exc}"
            raise
    return _OCR_ENGINE


def get_vietocr_predictor():
    global _VIETOCR_PREDICTOR, _VIETOCR_ERROR
    if _VIETOCR_PREDICTOR is not None:
        return _VIETOCR_PREDICTOR

    try:
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except Exception as exc:
        _VIETOCR_ERROR = f"import_error: {type(exc).__name__}: {exc}"
        return None

    config_name = os.getenv("VIETOCR_CONFIG", "vgg_transformer")
    device = os.getenv("VIETOCR_DEVICE", "cpu")
    beamsearch = os.getenv("VIETOCR_BEAMSEARCH", "false").lower() in {"1", "true", "yes"}

    try:
        config = Cfg.load_config_from_name(config_name)
        config["device"] = device
        config["predictor"]["beamsearch"] = beamsearch
        _VIETOCR_PREDICTOR = Predictor(config)
        _VIETOCR_ERROR = ""
        return _VIETOCR_PREDICTOR
    except Exception as exc:
        _VIETOCR_ERROR = f"init_error: {type(exc).__name__}: {exc}"
        return None


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _box_to_rect(box: Any) -> List[float]:
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return [min(xs), min(ys), max(xs), max(ys)]


def _crop_line(image: Image.Image, rect: List[float]) -> Image.Image:
    width, height = image.size
    x1, y1, x2, y2 = rect
    pad_x = max(4, int((x2 - x1) * 0.08))
    pad_y = max(4, int((y2 - y1) * 0.22))
    crop_box = (
        max(0, int(x1) - pad_x),
        max(0, int(y1) - pad_y),
        min(width, int(x2) + pad_x),
        min(height, int(y2) + pad_y),
    )
    return image.crop(crop_box).convert("RGB")


def _recognize_with_vietocr(image: Image.Image, rect: List[float]) -> str:
    predictor = get_vietocr_predictor()
    if predictor is None:
        return ""
    try:
        return _normalize_text(predictor.predict(_crop_line(image, rect)))
    except Exception:
        return ""


def extract_image_layout(image_path: str) -> Dict[str, Any]:
    image = Image.open(image_path)
    width, height = image.size
    recognizer = os.getenv("OCR_RECOGNIZER", "paddle").lower()
    if recognizer in {"vietocr", "hybrid"}:
        # Load Torch/VietOCR before PaddleOCR. On Windows, loading Paddle first
        # can make torch fail to load shm.dll in the same process.
        get_vietocr_predictor()

    paddle_started = time.perf_counter()
    result = get_ocr_engine().ocr(image_path, cls=True)
    paddle_elapsed = time.perf_counter() - paddle_started
    lines: List[Dict[str, Any]] = []
    vietocr_count = 0
    vietocr_started = time.perf_counter()

    for page_result in result or []:
        for item in page_result or []:
            if not item or len(item) < 2:
                continue
            box, payload = item[0], item[1]
            rect = _box_to_rect(box)
            paddle_text = _normalize_text(payload[0] if payload else "")
            vietocr_text = ""
            if recognizer in {"vietocr", "hybrid"}:
                vietocr_text = _recognize_with_vietocr(image, rect)
                if vietocr_text:
                    vietocr_count += 1

            text = vietocr_text if vietocr_text else paddle_text
            if not text:
                continue
            confidence = float(payload[1]) if payload and len(payload) > 1 else None
            lines.append(
                {
                    "text": text,
                    "bbox": rect,
                    "confidence": confidence,
                    "recognizer": "vietocr" if vietocr_text else "paddle",
                    "paddle_text": paddle_text if vietocr_text and paddle_text != vietocr_text else "",
                }
            )

    lines.sort(key=lambda line: (line["bbox"][1], line["bbox"][0]))
    vietocr_elapsed = time.perf_counter() - vietocr_started
    print(
        "[ocr_service] recognizer=%s lines=%s vietocr_lines=%s paddle_elapsed=%.2fs vietocr_elapsed=%.2fs"
        % (recognizer, len(lines), vietocr_count, paddle_elapsed, vietocr_elapsed),
        flush=True,
    )
    return {"pages": [{"page": 1, "width": width, "height": height, "lines": lines}]}


@app.get("/health")
def health() -> Dict[str, str]:
    recognizer = os.getenv("OCR_RECOGNIZER", "paddle").lower()
    vietocr_ready = bool(get_vietocr_predictor()) if recognizer in {"vietocr", "hybrid"} else False
    payload = {
        "status": "ok",
        "recognizer": recognizer,
        "vietocr_device": os.getenv("VIETOCR_DEVICE", "cpu"),
        "paddle": "ready" if _OCR_ENGINE is not None else "lazy",
        "vietocr": "ready" if vietocr_ready else "disabled_or_unavailable",
    }
    if _VIETOCR_ERROR:
        payload["vietocr_error"] = _VIETOCR_ERROR
    if _PADDLE_ERROR:
        payload["paddle_error"] = _PADDLE_ERROR
    return payload


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
