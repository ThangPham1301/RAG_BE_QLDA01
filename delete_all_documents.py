#!/usr/bin/env python
"""Delete ALL documents and reset."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.documents.models import Document

print("=" * 80)
print("DELETING ALL DOCUMENTS")
print("=" * 80)

all_docs = Document.objects.all()
count = all_docs.count()

print(f"\nDeleting {count} documents...")
for doc in all_docs:
    print(f"  - {doc.id}: {doc.title}")

all_docs.delete()
print("✓ All documents deleted!")
print("\nNow upload new documents via frontend.")
print("=" * 80)
