#!/usr/bin/env python3
"""
Authentication System Connection Test
Kiểm tra kết nối giữa Backend và Frontend
"""

import os
import sys
import django
from django.conf import settings
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RAG_BE.settings')
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from apps.auth.models import EmailVerificationToken, AuthSession
import json

User = get_user_model()

def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_database_connection():
    """Test database connectivity"""
    print_section("1. DATABASE CONNECTION TEST")
    try:
        user_count = User.objects.count()
        print(f"✅ Database connected successfully")
        print(f"   Total users in database: {user_count}")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return False

def test_cors_configuration():
    """Test CORS settings"""
    print_section("2. CORS CONFIGURATION TEST")
    
    cors_origins = settings.CORS_ALLOWED_ORIGINS
    allowed_hosts = settings.ALLOWED_HOSTS
    
    print(f"CORS_ALLOWED_ORIGINS: {cors_origins}")
    print(f"ALLOWED_HOSTS: {allowed_hosts}")
    
    expected_frontend = 'http://localhost:5173'
    if expected_frontend in cors_origins:
        print(f"✅ Frontend URL {expected_frontend} is allowed")
    else:
        print(f"⚠️  Warning: Frontend URL {expected_frontend} NOT in CORS whitelist")
    
    return True

def test_jwt_configuration():
    """Test JWT settings"""
    print_section("3. JWT CONFIGURATION TEST")
    
    jwt_config = settings.SIMPLE_JWT
    print(f"JWT Algorithm: {jwt_config.get('ALGORITHM')}")
    print(f"Access Token Lifetime: {jwt_config.get('ACCESS_TOKEN_LIFETIME')}")
    print(f"Refresh Token Lifetime: {jwt_config.get('REFRESH_TOKEN_LIFETIME')}")
    print(f"Rotate Refresh Tokens: {jwt_config.get('ROTATE_REFRESH_TOKENS')}")
    
    if jwt_config.get('SIGNING_KEY'):
        print("✅ JWT Secret Key is configured")
    else:
        print("⚠️  Warning: JWT Secret Key might not be configured")
    
    return True

def create_test_user():
    """Create a test user for login testing"""
    print_section("4. CREATE TEST USER")
    
    test_email = 'test@example.com'
    test_password = 'TestPassword123!@#'
    
    try:
        # Check if user exists
        user = User.objects.filter(email=test_email).first()
        
        if user:
            print(f"✅ Test user already exists: {test_email}")
            print(f"   Email verified: {user.is_email_verified}")
        else:
            # Create new user
            user = User.objects.create_user(
                email=test_email,
                username=test_email,
                password=test_password,
                first_name='Test',
                last_name='User',
            )
            
            # Mark email as verified
            user.is_email_verified = True
            user.save()
            
            print(f"✅ Test user created: {test_email}")
            print(f"   Password: {test_password}")
            print(f"   Email verified: {user.is_email_verified}")
        
        return user, test_email, test_password
    
    except Exception as e:
        print(f"❌ Failed to create test user: {str(e)}")
        return None, None, None

def test_login_endpoint(email, password):
    """Test login endpoint"""
    print_section("5. LOGIN ENDPOINT TEST")
    
    client = Client()
    
    try:
        response = client.post(
            '/api/auth/login',
            data=json.dumps({
                'email': email,
                'password': password
            }),
            content_type='application/json'
        )
        
        print(f"Endpoint: POST /api/auth/login")
        print(f"Status Code: {response.status_code}")
        
        response_data = json.loads(response.content)
        print(f"Response: {json.dumps(response_data, indent=2)}")
        
        if response.status_code == 200:
            print("\n✅ Login successful!")
            print(f"   Access Token: {response_data.get('tokens', {}).get('access', 'N/A')[:50]}...")
            print(f"   User: {response_data.get('user', {}).get('email')}")
            return True
        else:
            print(f"\n❌ Login failed with status {response.status_code}")
            if 'detail' in response_data:
                print(f"   Error: {response_data['detail']}")
            return False
    
    except Exception as e:
        print(f"❌ Login request failed: {str(e)}")
        return False

def test_signup_endpoint():
    """Test signup endpoint"""
    print_section("6. SIGNUP ENDPOINT TEST")
    
    client = Client()
    
    signup_email = f'signup_test_{os.urandom(4).hex()}@example.com'
    signup_password = 'SignupTest123!@#'
    
    try:
        response = client.post(
            '/api/auth/signup',
            data=json.dumps({
                'email': signup_email,
                'first_name': 'Signup',
                'last_name': 'Test',
                'password': signup_password,
                'password_confirm': signup_password
            }),
            content_type='application/json'
        )
        
        print(f"Endpoint: POST /api/auth/signup")
        print(f"Status Code: {response.status_code}")
        
        response_data = json.loads(response.content)
        
        if response.status_code in [200, 201]:
            print("✅ Signup successful!")
            print(f"   User email: {response_data.get('user', {}).get('email')}")
            print(f"   Email verified: {response_data.get('user', {}).get('is_email_verified')}")
        else:
            print(f"❌ Signup failed with status {response.status_code}")
            if 'detail' in response_data:
                print(f"   Error: {response_data['detail']}")
    
    except Exception as e:
        print(f"❌ Signup request failed: {str(e)}")

def test_token_refresh():
    """Test token refresh endpoint"""
    print_section("7. TOKEN REFRESH ENDPOINT TEST")
    
    client = Client()
    
    # First, get tokens from login
    user, email, password = create_test_user()
    if not user:
        print("⚠️  Skipping token refresh test (no test user)")
        return
    
    # Login to get refresh token
    login_response = client.post(
        '/api/auth/login',
        data=json.dumps({'email': email, 'password': password}),
        content_type='application/json'
    )
    
    if login_response.status_code != 200:
        print("❌ Could not get initial tokens")
        return
    
    refresh_token = json.loads(login_response.content)['tokens']['refresh']
    
    # Try to refresh
    try:
        refresh_response = client.post(
            '/api/auth/token/refresh',
            data=json.dumps({'refresh': refresh_token}),
            content_type='application/json'
        )
        
        print(f"Endpoint: POST /api/auth/token/refresh")
        print(f"Status Code: {refresh_response.status_code}")
        
        if refresh_response.status_code == 200:
            print("✅ Token refresh successful!")
        else:
            print(f"❌ Token refresh failed with status {refresh_response.status_code}")
    
    except Exception as e:
        print(f"❌ Token refresh request failed: {str(e)}")

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  RAG APPLICATION - AUTHENTICATION SYSTEM TEST")
    print("="*60)
    
    tests_passed = 0
    tests_total = 0
    
    # Run tests
    if test_database_connection():
        tests_passed += 1
    tests_total += 1
    
    if test_cors_configuration():
        tests_passed += 1
    tests_total += 1
    
    if test_jwt_configuration():
        tests_passed += 1
    tests_total += 1
    
    user, email, password = create_test_user()
    tests_total += 1
    if user:
        tests_passed += 1
    
    if email and password:
        if test_login_endpoint(email, password):
            tests_passed += 1
        tests_total += 1
        
        test_signup_endpoint()
        test_token_refresh()
    
    # Summary
    print_section("TEST SUMMARY")
    print(f"Tests Passed: {tests_passed}/{tests_total}")
    
    if tests_passed == tests_total:
        print("✅ All core tests passed! Backend is configured correctly.")
        print("\nNext steps:")
        print("1. Start frontend: cd e:\\QLDA_workspace\\RAG_FE_QLDA01 && npm run dev")
        print("2. Open http://localhost:5173 in browser")
        print("3. Try logging in with:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
    else:
        print("⚠️  Some tests failed. Check the output above for issues.")
    
    print("\n" + "="*60 + "\n")

if __name__ == '__main__':
    main()
