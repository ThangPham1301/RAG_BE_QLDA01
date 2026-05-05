#!/usr/bin/env python
"""Helper script to create test users for API testing"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from apps.auth.models import User

if len(sys.argv) < 3:
    print("Usage: python create_test_user.py <email> <password>")
    sys.exit(1)

email = sys.argv[1]
password = sys.argv[2]

try:
    # Check if user exists
    try:
        user = User.objects.get(email=email)
        # User exists, just update password and verification status
        user.set_password(password)
        user.is_email_verified = True
        user.save()
        print(f"UPDATED:{user.id}")
    except User.DoesNotExist:
        # Create new user
        import uuid
        user = User.objects.create(
            id=uuid.uuid4(),
            email=email,
            first_name='Test',
            last_name='User',
            username=f'testuser_{uuid.uuid4().hex[:8]}'
        )
        user.set_password(password)
        user.is_email_verified = True
        user.save()
        print(f"CREATED:{user.id}")
        
except Exception as e:
    print(f"ERROR:{str(e)}")
    sys.exit(1)
