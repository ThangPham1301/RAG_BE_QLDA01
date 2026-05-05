#!/usr/bin/env python
"""Final test: Extract DOCX + text-based PDFs."""
import os
import sys
import django
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.documents.parser import extract_text_from_pdf
from apps.documents.services import _extract_text_from_docx, _extract_text_from_txt
from apps.documents.models import Document

print("=" * 80)
print("EXTRACTION TEST: DOCX + Text-based PDF")
print("=" * 80)

# Only test text-based PDFs (not image-scanned like 293.pdf)
test_files = [
    'media/documents/2026/05/VanBan_ChuyenDoi.pdf',
    'media/documents/2026/05/VanBan_ChuyenDoi2.pdf',
    'media/documents/2026/05/VanBan_ChuyenDoi3.pdf',
]

# Find DOCX files
docx_files = list(Path('media/documents').glob('**/*.docx'))
test_files.extend([str(f) for f in docx_files])

if not test_files:
    print("No test files found (DOCX or text PDFs)")
    sys.exit(1)

print(f"Testing {len(test_files)} files:\n")

passed = 0
failed = 0

for file_path in test_files:
    p = Path(file_path)
    if not p.exists():
        print(f"✗ {p.name}: FILE NOT FOUND")
        failed += 1
        continue
    
    file_size = p.stat().st_size
    suffix = p.suffix.lower()
    
    try:
        if suffix == '.pdf':
            text = extract_text_from_pdf(file_path)
        elif suffix == '.docx':
            text = _extract_text_from_docx(file_path)
        elif suffix == '.txt':
            text = _extract_text_from_txt(file_path)
        else:
            print(f"✗ {p.name}: Unknown file type")
            failed += 1
            continue
        
        text_len = len(text) if text else 0
        
        if text_len > 0:
            print(f"✓ {p.name} ({suffix})")
            print(f"  Size: {file_size} bytes → Text: {text_len} chars")
            print(f"  Preview: {text[:80]}...\n")
            passed += 1
        else:
            print(f"✗ {p.name}: No text extracted (0 chars)\n")
            failed += 1
    
    except Exception as e:
        print(f"✗ {p.name}: {str(e)[:100]}\n")
        failed += 1

print("=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 80)

if failed > 0:
    sys.exit(1)
