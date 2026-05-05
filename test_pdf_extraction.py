#!/usr/bin/env python
"""Test PDF extraction to debug extraction issues."""
import os
import sys
import django
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.documents.parser import extract_text_from_pdf
from apps.documents.models import Document

print("=" * 80)
print("PDF EXTRACTION TEST")
print("=" * 80)

# Test 1: Check if fitz is available
try:
    import fitz
    print(f"✓ PyMuPDF (fitz) imported successfully: version {fitz.version}")
except Exception as e:
    print(f"✗ PyMuPDF import failed: {e}")
    sys.exit(1)

# Test 2: Find PDFs in media directory
media_dir = Path('media/documents')
if media_dir.exists():
    pdfs = list(media_dir.glob('**/*.pdf'))
    print(f"\n✓ Found {len(pdfs)} PDF files in {media_dir}")
else:
    print(f"\n✗ Media directory not found: {media_dir}")
    sys.exit(1)

if not pdfs:
    print("✗ No PDF files found to test")
    sys.exit(1)

# Test 3: Extract from each PDF
for pdf_path in pdfs:
    print(f"\n{'─' * 80}")
    print(f"Testing: {pdf_path.name}")
    print(f"Full path: {pdf_path.absolute()}")
    print(f"File size: {pdf_path.stat().st_size} bytes")
    
    try:
        text = extract_text_from_pdf(str(pdf_path))
        text_len = len(text) if text else 0
        
        if text_len > 0:
            print(f"✓ Extraction successful: {text_len} chars")
            print(f"\nFirst 300 chars:")
            print(text[:300])
        else:
            print(f"✗ Extraction returned empty string (0 chars)")
            
            # Try to debug with fitz directly
            print("\nDebug with fitz directly:")
            try:
                doc = fitz.open(str(pdf_path))
                print(f"  - PDF pages: {len(doc)}")
                for i, page in enumerate(doc):
                    page_text = page.get_text()
                    print(f"  - Page {i}: {len(page_text)} chars")
            except Exception as de:
                print(f"  - Fitz error: {de}")
    except Exception as e:
        print(f"✗ Extraction error: {e}")
        import traceback
        traceback.print_exc()

# Test 4: Check database documents
print(f"\n{'─' * 80}")
print("Database Document Status:")
failed_docs = Document.objects.filter(index_status='failed')
print(f"Failed documents: {failed_docs.count()}")
for doc in failed_docs:
    print(f"\n  - ID {doc.id}: {doc.title}")
    print(f"    File: {doc.file.name if doc.file else 'None'}")
    print(f"    Error: {doc.index_error[:100]}")
    if doc.file:
        full_path = doc.file.path
        exists = Path(full_path).exists()
        print(f"    File exists: {exists}")
        if exists:
            size = Path(full_path).stat().st_size
            print(f"    File size: {size} bytes")

print("\n" + "=" * 80)
