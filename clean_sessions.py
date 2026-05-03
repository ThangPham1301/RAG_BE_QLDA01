#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.auth.models import AuthSession

# Delete all sessions with empty/null refresh_token
deleted_count, _ = AuthSession.objects.filter(refresh_token='').delete()
print(f"✅ Deleted {deleted_count} old sessions with empty refresh_token")

# Check remaining
remaining = AuthSession.objects.count()
print(f"✅ Remaining sessions: {remaining}")
