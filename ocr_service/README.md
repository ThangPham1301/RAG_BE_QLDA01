# OCR Service

FastAPI service rieng cho PaddleOCR. Service nay dung virtualenv rieng de tranh xung dot `protobuf` voi backend Django/Chroma.

## Setup Windows

```powershell
cd ocr_service
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
uvicorn app:app --host 127.0.0.1 --port 8100
```

Health check:

```text
GET http://127.0.0.1:8100/health
```

OCR image endpoint:

```text
POST http://127.0.0.1:8100/ocr/image
multipart form field: file
```

Backend Django se render PDF page thanh anh bang PyMuPDF, gui anh sang endpoint nay, roi nhan lai OCR layout JSON.
