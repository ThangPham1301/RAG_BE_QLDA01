# Authentication System - Code Templates & Quick Reference

## 1. REQUIRED PACKAGES (requirements.txt)

```
# Core
Django==4.2.29
djangorestframework==3.14.0
djangorestframework-simplejwt==5.3.2
django-cors-headers==4.3.1
django-environ==0.11.2
psycopg2-binary==2.9.9

# Security
django-ratelimit==4.1.0
cryptography==41.0.7
bcrypt==4.1.1
email-validator==2.1.0

# OAuth
google-auth==2.25.2
google-auth-oauthlib==1.2.0
requests==2.31.0

# Email
django-anymail==10.2

# Testing
pytest==7.4.3
pytest-django==4.7.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==22.0.0

# Monitoring
sentry-sdk==1.38.0
```

## 2. PROJECT STRUCTURE - QUICK CREATE

```bash
# 1. Create apps directory
mkdir -p apps/auth/tests
mkdir -p apps/auth/migrations

# 2. Create __init__.py files
touch apps/__init__.py
touch apps/auth/__init__.py
touch apps/auth/tests/__init__.py
touch apps/auth/migrations/__init__.py

# 3. Create app files
touch apps/auth/models.py
touch apps/auth/serializers.py
touch apps/auth/views.py
touch apps/auth/urls.py
touch apps/auth/services.py
touch apps/auth/permissions.py
touch apps/auth/middleware.py
touch apps/auth/exceptions.py
touch apps/auth/utils.py
touch apps/auth/admin.py
touch apps/auth/apps.py

# 4. Create test files
touch apps/auth/tests/test_models.py
touch apps/auth/tests/test_serializers.py
touch apps/auth/tests/test_views.py
touch apps/auth/tests/test_services.py
touch apps/auth/tests/test_integrations.py
touch apps/auth/tests/conftest.py
touch apps/auth/tests/factories.py
```

## 3. MODELS - BOILERPLATE CODE

### apps/auth/models.py

```python
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
import uuid

class User(AbstractUser):
    """Extended User model with OAuth and email verification support."""

    # Core fields
    phone_number = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(blank=True)
    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # OAuth
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    google_auth_token = models.TextField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['google_id']),
            models.Index(fields=['is_email_verified']),
        ]

    def __str__(self):
        return self.email


class EmailVerificationToken(models.Model):
    """Email verification token for signup flow."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='email_token')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'email_verification_tokens'
        indexes = [models.Index(fields=['user_id', 'is_used'])]

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class OTPToken(models.Model):
    """One-time password tokens for email/SMS verification."""

    TYPE_CHOICES = [
        ('email_verification', 'Email Verification'),
        ('password_reset', 'Password Reset'),
        ('two_factor', 'Two-Factor Authentication'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_tokens')
    code = models.CharField(max_length=6)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.IntegerField(default=0)

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'otp_tokens'
        unique_together = [['user_id', 'type', 'is_used']]
        indexes = [
            models.Index(fields=['user_id', 'is_used']),
            models.Index(fields=['expires_at']),
        ]

    def is_valid(self):
        return (
            not self.is_used
            and self.attempt_count < 5
            and timezone.now() < self.expires_at
        )

    def is_expired(self):
        return timezone.now() > self.expires_at


class PasswordResetToken(models.Model):
    """Password reset tokens with single-use restriction."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            models.Index(fields=['user_id', 'is_used']),
            models.Index(fields=['expires_at']),
        ]

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class AuthSession(models.Model):
    """Track user authentication sessions and tokens."""

    TOKEN_TYPE_CHOICES = [
        ('access', 'Access Token'),
        ('refresh', 'Refresh Token'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_sessions')
    token = models.CharField(max_length=500, unique=True, db_index=True)
    token_type = models.CharField(max_length=20, choices=TOKEN_TYPE_CHOICES)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_info = models.JSONField(default=dict)

    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auth_sessions'
        indexes = [
            models.Index(fields=['user_id', 'is_revoked']),
            models.Index(fields=['expires_at']),
        ]

    def is_valid(self):
        return (
            not self.is_revoked
            and timezone.now() < self.expires_at
        )
```

## 4. SERIALIZERS - BOILERPLATE CODE

### apps/auth/serializers.py

```python
from rest_framework import serializers
from django.contrib.auth import authenticate
from email_validator import validate_email, EmailNotValidError
from apps.auth.models import User

class SignUpSerializer(serializers.Serializer):
    """Serializer for user registration."""

    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    phone_number = serializers.CharField(max_length=20, required=False)

    def validate_email(self, value):
        """Validate email format and uniqueness."""
        try:
            validate_email(value.lower())
        except EmailNotValidError:
            raise serializers.ValidationError("Invalid email format.")

        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("Email already registered.")

        return value.lower()

    def validate_password(self, value):
        """Validate password strength."""
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters.")
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError("Password must contain uppercase letters.")
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError("Password must contain digits.")
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in value):
            raise serializers.ValidationError("Password must contain special characters.")
        return value

    def validate(self, data):
        """Validate password match."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return data

    def create(self, validated_data):
        """Create new user."""
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        """Authenticate user."""
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        data['user'] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user data."""

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number',
                  'avatar_url', 'is_email_verified', 'created_at']
        read_only_fields = ['id', 'created_at']


class VerifyEmailSerializer(serializers.Serializer):
    """Serializer for email verification."""

    token = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""

    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate(self, data):
        if data['new_password'] != data['password_confirm']:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return data


class OTPVerifySerializer(serializers.Serializer):
    """Serializer for OTP verification."""

    otp_code = serializers.CharField(max_length=6)
    otp_type = serializers.ChoiceField(
        choices=['email_verification', 'password_reset', 'two_factor']
    )
```

## 5. VIEWS - BOILERPLATE CODE

### apps/auth/views.py

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils import timezone
from datetime import timedelta

from apps.auth.models import User, EmailVerificationToken, OTPToken, PasswordResetToken
from apps.auth.serializers import (
    SignUpSerializer, LoginSerializer, UserSerializer,
    VerifyEmailSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, OTPVerifySerializer
)
from apps.auth.services import (
    AuthService, OTPService, EmailService, TokenService
)
from apps.auth.exceptions import AuthenticationError, InvalidTokenError
from apps.auth.utils import get_client_ip


class SignUpView(APIView):
    """User registration endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()

        # Generate and send email verification token
        email_service = EmailService()
        email_token = email_service.generate_verification_token(user)
        email_service.send_verification_email(user, email_token)

        return Response(
            {
                'success': True,
                'message': 'Sign up successful. Please verify your email.',
                'data': {
                    'user_id': user.id,
                    'email': user.email,
                    'is_email_verified': user.is_email_verified
                }
            },
            status=status.HTTP_201_CREATED
        )


class VerifyEmailView(APIView):
    """Email verification endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        token = serializer.validated_data['token']

        try:
            email_token = EmailVerificationToken.objects.get(token=token)
            if not email_token.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Invalid or expired token'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Mark as used and verified
            user = email_token.user
            user.is_email_verified = True
            user.email_verified_at = timezone.now()
            user.save()

            email_token.is_used = True
            email_token.used_at = timezone.now()
            email_token.save()

            return Response(
                {
                    'success': True,
                    'message': 'Email verified successfully'
                }
            )

        except EmailVerificationToken.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid token'
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class LoginView(APIView):
    """User login endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Invalid email or password'
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        user = serializer.validated_data['user']

        # Generate tokens
        token_service = TokenService()
        access_token = token_service.generate_access_token(user)
        refresh_token = token_service.generate_refresh_token(user)

        # Log session
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        return Response(
            {
                'success': True,
                'message': 'Login successful',
                'data': {
                    'user': UserSerializer(user).data,
                    'tokens': {
                        'access_token': access_token,
                        'refresh_token': refresh_token,
                        'token_type': 'Bearer',
                        'expires_in': 3600
                    }
                }
            }
        )


class LogoutView(APIView):
    """User logout endpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        revoke_all = request.data.get('revoke_all_sessions', False)

        if revoke_all:
            # Revoke all sessions for this user
            from apps.auth.models import AuthSession
            AuthSession.objects.filter(
                user=user,
                is_revoked=False
            ).update(
                is_revoked=True,
                revoked_at=timezone.now()
            )

        return Response(
            {
                'success': True,
                'message': 'Logged out successfully'
            }
        )


class PasswordResetRequestView(APIView):
    """Request password reset endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']

        # Always return success for security (don't reveal if email exists)
        try:
            user = User.objects.get(email=email)
            email_service = EmailService()
            reset_token = email_service.generate_password_reset_token(user)
            email_service.send_password_reset_email(user, reset_token)
        except User.DoesNotExist:
            pass  # Silently fail for security

        return Response(
            {
                'success': True,
                'message': 'Password reset email sent'
            }
        )


class PasswordResetConfirmView(APIView):
    """Confirm password reset endpoint."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']

        try:
            reset_token = PasswordResetToken.objects.get(token=token)
            if not reset_token.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Invalid or expired token'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = reset_token.user
            user.set_password(new_password)
            user.save()

            reset_token.is_used = True
            reset_token.used_at = timezone.now()
            reset_token.save()

            return Response(
                {
                    'success': True,
                    'message': 'Password reset successfully'
                }
            )

        except PasswordResetToken.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid token'
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class OTPVerifyView(APIView):
    """OTP verification endpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'Validation failed',
                    'errors': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        otp_code = serializer.validated_data['otp_code']
        otp_type = serializer.validated_data['otp_type']

        try:
            otp_token = OTPToken.objects.get(
                user=user,
                code=otp_code,
                type=otp_type,
                is_used=False
            )

            if not otp_token.is_valid():
                return Response(
                    {
                        'success': False,
                        'message': 'Invalid or expired OTP'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            otp_token.is_used = True
            otp_token.used_at = timezone.now()
            otp_token.save()

            return Response(
                {
                    'success': True,
                    'message': 'OTP verified successfully'
                }
            )

        except OTPToken.DoesNotExist:
            return Response(
                {
                    'success': False,
                    'message': 'Invalid OTP code'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
```

## 6. URLS CONFIGURATION

### apps/auth/urls.py

```python
from django.urls import path
from apps.auth import views

app_name = 'auth'

urlpatterns = [
    # Authentication
    path('sign-up', views.SignUpView.as_view(), name='sign-up'),
    path('login', views.LoginView.as_view(), name='login'),
    path('logout', views.LogoutView.as_view(), name='logout'),

    # Email Verification
    path('verify-email', views.VerifyEmailView.as_view(), name='verify-email'),

    # Password Reset
    path('password-reset/request', views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # OTP
    path('verify-otp', views.OTPVerifyView.as_view(), name='verify-otp'),

    # OAuth (to be implemented)
    # path('google/callback', views.GoogleCallbackView.as_view(), name='google-callback'),
]
```

### RAG_BE/urls.py

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.auth.urls')),
]
```

## 7. MIDDLEWARE & UTILITIES

### apps/auth/exceptions.py

```python
from rest_framework.exceptions import APIException
from rest_framework import status

class AuthenticationError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Authentication failed.'

class InvalidTokenError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid token.'

class RateLimitExceeded(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = 'Too many requests. Please try again later.'
```

### apps/auth/utils.py

```python
import secrets
import hashlib
import string
from django.utils import timezone
from datetime import timedelta

def generate_token(length=32):
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)

def hash_token(token):
    """Hash a token using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()

def verify_token(stored_hash, provided_token):
    """Verify a token against its hash."""
    provided_hash = hash_token(provided_token)
    return secrets.compare_digest(stored_hash, provided_hash)

def generate_otp(length=6):
    """Generate a numeric OTP code."""
    digits = string.digits
    return ''.join(secrets.choice(digits) for _ in range(length))

def get_token_expiry(hours=24):
    """Get token expiry datetime."""
    return timezone.now() + timedelta(hours=hours)

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
```

## 8. MIGRATION COMMANDS

```bash
# Create migration file
python manage.py makemigrations auth

# Apply migrations
python manage.py migrate auth

# Show migration plan
python manage.py showmigrations auth

# Reverse migration
python manage.py migrate auth 0001
```

## 9. TESTING CHECKLIST

```bash
# Run all tests
pytest apps/auth/tests/ -v --tb=short

# Run with coverage
pytest apps/auth/tests/ --cov=apps.auth --cov-report=html

# Run specific test class
pytest apps/auth/tests/test_views.py::TestSignUpView -v

# Run specific test method
pytest apps/auth/tests/test_views.py::TestSignUpView::test_sign_up_success -v

# Run with detailed output
pytest apps/auth/tests/ -vv -s

# Stop on first failure
pytest apps/auth/tests/ -x
```

## 10. DEPLOYMENT CHECKLIST

```bash
# 1. Collect static files
python manage.py collectstatic --noinput

# 2. Run migrations
python manage.py migrate

# 3. Create superuser (first deployment only)
python manage.py createsuperuser

# 4. Check deployment readiness
python manage.py check --deploy

# 5. Run tests
pytest apps/auth/tests/ --cov=apps.auth

# 6. Load fixtures (if needed)
python manage.py loaddata initial_data
```

## 11. COMMON COMMANDS REFERENCE

```bash
# Development server
python manage.py runserver

# Shell access
python manage.py shell

# Create app
python manage.py startapp appname

# Database shell
python manage.py dbshell

# Flush database
python manage.py flush

# Create superuser
python manage.py createsuperuser

# Test coverage
pytest --cov=apps.auth --cov-report=html

# Format code
black apps/auth/

# Lint
flake8 apps/auth/

# Type checking
mypy apps/auth/
```

## 12. DEBUGGING TIPS

### Django Debug Toolbar

```bash
pip install django-debug-toolbar
```

```python
# settings.py
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INTERNAL_IPS = ['127.0.0.1']
```

### Logs

```python
# apps/auth/views.py
import logging

logger = logging.getLogger(__name__)

logger.info(f"User {user.email} logged in from {ip_address}")
logger.error(f"Failed login attempt for {email}")
logger.warning(f"OTP verification failed for {user.id}")
```

### Database Queries

```python
from django.db import connection
from django.test.utils import override_settings

# Print queries
print(connection.queries)

# Count queries
with override_settings(DEBUG=True):
    # code that queries database
    print(len(connection.queries))
```

---

**Next Steps:**

1. Copy this code into respective files
2. Adjust according to your specific needs
3. Run migrations
4. Write tests first (TDD)
5. Implement views and services
6. Test thoroughly before deployment
