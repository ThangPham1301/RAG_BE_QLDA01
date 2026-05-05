#!/usr/bin/env python
"""Clean up failed documents."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.documents.models import Document

print("=" * 80)
print("DOCUMENT CLEANUP")
print("=" * 80)

# Delete failed documents
failed = Document.objects.filter(index_status='failed')
count = failed.count()

if count > 0:
    print(f"\nDeleting {count} failed documents:")
    for doc in failed:
        print(f"  - {doc.id}: {doc.title}")
    failed.delete()
    print("✓ Deleted!")
else:
    print("\nNo failed documents to delete")

# Show current status
print("\n" + "=" * 80)
print("CURRENT DOCUMENTS:")
print("=" * 80)

all_docs = Document.objects.all().select_related('chat_session').order_by('-uploaded_at')

if not all_docs.exists():
    print("No documents in database")
else:
    for doc in all_docs:
        status_icon = "✓" if doc.index_status == "indexed" else "✗"
        print(f"\n{status_icon} ID {doc.id}: {doc.title}")
        print(f"  Session: {doc.chat_session.title}")
        print(f"  Status: {doc.index_status}")
        print(f"  Chunks: {doc.indexed_chunks}")
        if doc.index_error:
            print(f"  Error: {doc.index_error[:80]}")

print("\n" + "=" * 80)
