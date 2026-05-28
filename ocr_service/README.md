# OCR Service

FastAPI service rieng cho OCR. Service nay dung virtualenv rieng de tranh xung dot `protobuf` voi backend Django/Chroma.

Mac dinh service dung PaddleOCR cho ca detection va recognition. Co the bat VietOCR o che do hybrid: PaddleOCR detect vung chu/toa do, VietOCR doc text tren tung crop.

## Setup Windows

```powershell
cd ocr_service
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Optional VietOCR:

```powershell
pip install -r requirements-vietocr.txt
```

Install PyTorch CPU neu khong dung GPU:

```powershell
pip install torch torchvision
```

Install PyTorch CUDA neu dung GPU NVIDIA. Chon CUDA wheel theo trang cai dat chinh thuc cua PyTorch; vi du voi CUDA 12.1:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Kiem tra PyTorch thay GPU:

```powershell
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

## Run

```powershell
uvicorn app:app --host 127.0.0.1 --port 8100
```

Run voi VietOCR hybrid:

```powershell
$env:OCR_RECOGNIZER="hybrid"
$env:VIETOCR_DEVICE="cpu"
uvicorn app:app --host 127.0.0.1 --port 8100
```

Neu may co CUDA va torch CUDA tuong ung:

```powershell
$env:VIETOCR_DEVICE="cuda"
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
