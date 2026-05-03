# Authentication System Implementation Plan

## Executive Summary

Kế hoạch xây dựng **authentication system hoàn chỉnh** cho Django RAG backend, hỗ trợ email/password, Google OAuth, OTP verification, password reset, và session management. Kiến trúc monolith với PostgreSQL và TDD approach.

---

## 1. REQUIREMENTS ANALYSIS

### 1.1 Functional Requirements

| Feature                | Scope                   | Priority | Complexity |
| ---------------------- | ----------------------- | -------- | ---------- |
| Email/Password Sign Up | Email verification      | HIGH     | Medium     |
| Email/Password Sign In | Session management      | HIGH     | Low        |
| Google OAuth 2.0       | Third-party integration | HIGH     | High       |
| Logout                 | Destroy all sessions    | HIGH     | Low        |
| Password Reset         | Token-based flow        | HIGH     | Medium     |
| OTP Verification       | SMS/Email-based         | MEDIUM   | Medium     |
| Session Management     | Token + DB sessions     | HIGH     | Medium     |
| Rate Limiting          | Brute force protection  | HIGH     | Low        |
| Two-Factor Auth (2FA)  | Optional enhancement    | LOW      | High       |

### 1.2 Non-Functional Requirements

- **Security**: No plaintext passwords, CSRF protection, rate limiting
- **Performance**: <200ms response time for auth endpoints
- **Scalability**: Stateless token-based auth (JWT or DRF tokens)
- **Compliance**: GDPR-compliant data handling
- **Testability**: 80%+ unit + integration test coverage

---

## 2. DATABASE ARCHITECTURE

### 2.1 Models & Schema

#### 2.1.1 User Model (extends Django's AbstractUser)

```python
class User(AbstractUser):
    # Core fields (inherited: username, email, first_name, last_name, password)
    phone_number = CharField(max_length=20, blank=True)
    avatar_url = URLField(blank=True)
    is_email_verified = BooleanField(default=False)
    email_verified_at = DateTimeField(null=True, blank=True)

    # OAuth fields
    google_id = CharField(max_length=255, unique=True, null=True, blank=True)
    google_auth_token = TextField(null=True, blank=True)

    # Status
    is_active = BooleanField(default=True)
    last_login = DateTimeField(null=True, blank=True)

    # Metadata
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            Index(fields=['email']),
            Index(fields=['google_id']),
            Index(fields=['is_email_verified']),
        ]
```

#### 2.1.2 EmailVerificationToken Model

```python
class EmailVerificationToken(Model):
    user = OneToOneField(User, on_delete=CASCADE, related_name='email_token')
    token = CharField(max_length=255, unique=True, db_index=True)
    token_hash = CharField(max_length=255, unique=True)  # bcrypt for security
    expires_at = DateTimeField()
    is_used = BooleanField(default=False)
    used_at = DateTimeField(null=True)

    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'email_verification_tokens'
        indexes = [Index(fields=['user_id', 'is_used'])]
```

#### 2.1.3 OTPToken Model

```python
class OTPToken(Model):
    OTP_TYPE_CHOICES = [
        ('email_verification', 'Email Verification'),
        ('password_reset', 'Password Reset'),
        ('two_factor', 'Two-Factor Authentication'),
    ]

    user = ForeignKey(User, on_delete=CASCADE, related_name='otp_tokens')
    code = CharField(max_length=6)  # 6-digit numeric OTP
    type = CharField(max_length=20, choices=OTP_TYPE_CHOICES)
    is_used = BooleanField(default=False)
    used_at = DateTimeField(null=True)
    attempt_count = IntegerField(default=0, max_value=5)

    expires_at = DateTimeField()
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'otp_tokens'
        unique_together = [['user_id', 'type', 'is_used']]
        indexes = [
            Index(fields=['user_id', 'is_used']),
            Index(fields=['expires_at']),
        ]
```

#### 2.1.4 PasswordResetToken Model

```python
class PasswordResetToken(Model):
    user = ForeignKey(User, on_delete=CASCADE, related_name='password_reset_tokens')
    token = CharField(max_length=255, unique=True, db_index=True)
    token_hash = CharField(max_length=255, unique=True)
    expires_at = DateTimeField()
    is_used = BooleanField(default=False)
    used_at = DateTimeField(null=True)
    ip_address = GenericIPAddressField(null=True)

    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            Index(fields=['user_id', 'is_used']),
            Index(fields=['expires_at']),
        ]
```

#### 2.1.5 Session Model (custom for token tracking)

```python
class AuthSession(Model):
    user = ForeignKey(User, on_delete=CASCADE, related_name='auth_sessions')
    token = CharField(max_length=500, unique=True, db_index=True)
    token_type = CharField(max_length=20, choices=[
        ('access', 'Access Token'),
        ('refresh', 'Refresh Token'),
    ])
    ip_address = GenericIPAddressField()
    user_agent = TextField()
    device_info = JSONField(default=dict)

    expires_at = DateTimeField()
    is_revoked = BooleanField(default=False)
    revoked_at = DateTimeField(null=True)

    created_at = DateTimeField(auto_now_add=True)
    last_used_at = DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auth_sessions'
        indexes = [
            Index(fields=['user_id', 'is_revoked']),
            Index(fields=['expires_at']),
        ]
```

### 2.2 Migration Strategy

- **Approach**: Django's code-first migrations
- **Database**: PostgreSQL with automatic migrations
- **Sequence**:
  1. Create User model (extend AbstractUser)
  2. Create EmailVerificationToken
  3. Create OTPToken
  4. Create PasswordResetToken
  5. Create AuthSession
  6. Add indexes & constraints

---

## 3. PROJECT ARCHITECTURE

### 3.1 Directory Structure

```
RAG_BE/
├── RAG_BE/
│   ├── settings.py         (updated: DB, installed apps, middleware, env vars)
│   ├── urls.py             (updated: include auth urls)
│   └── asgi.py / wsgi.py
├── apps/
│   ├── auth/
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_otptoken.py
│   │   │   └── ...
│   │   ├── models.py       (User, OTPToken, PasswordResetToken, EmailVerificationToken, AuthSession)
│   │   ├── views.py        (APIViews: signup, login, logout, verify-email, password-reset, otp)
│   │   ├── serializers.py  (DRF serializers with validation)
│   │   ├── urls.py         (API routes)
│   │   ├── services.py     (business logic: OTP, token generation, email)
│   │   ├── permissions.py  (custom permissions: IsAuthenticated, IsEmailVerified)
│   │   ├── middleware.py   (token verification, rate limiting)
│   │   ├── exceptions.py   (custom exceptions & error responses)
│   │   ├── utils.py        (token generation, hashing utilities)
│   │   ├── tests/
│   │   │   ├── test_models.py
│   │   │   ├── test_views.py
│   │   │   ├── test_services.py
│   │   │   └── test_integrations.py
│   │   ├── admin.py
│   │   └── apps.py
│   └── __init__.py
├── requirements.txt        (dependencies)
├── .env.example            (environment variables template)
├── .env                    (local development only, git-ignored)
└── manage.py
```

### 3.2 Module Responsibilities

| Module             | Responsibility                  | Key Classes/Functions                                                                |
| ------------------ | ------------------------------- | ------------------------------------------------------------------------------------ |
| **models.py**      | Database entities               | User, OTPToken, PasswordResetToken, EmailVerificationToken, AuthSession              |
| **serializers.py** | Input validation, serialization | SignUpSerializer, LoginSerializer, VerifyEmailSerializer, ResetPasswordSerializer    |
| **views.py**       | HTTP request handlers           | SignUpView, LoginView, LogoutView, VerifyEmailView, PasswordResetView, OTPVerifyView |
| **services.py**    | Business logic                  | AuthService, OTPService, EmailService, TokenService                                  |
| **permissions.py** | Access control                  | IsAuthenticated, IsEmailVerified, IsOTPVerified                                      |
| **middleware.py**  | Request preprocessing           | TokenAuthenticationMiddleware, RateLimitMiddleware                                   |
| **utils.py**       | Helper functions                | generate_token(), hash_token(), verify_token(), generate_otp()                       |
| **exceptions.py**  | Error handling                  | AuthenticationError, InvalidTokenError, RateLimitExceeded                            |

---

## 4. API ENDPOINTS DESIGN

### 4.1 Base URL

```
/api/v1/auth/
```

### 4.2 Endpoint Specifications

#### 4.2.1 User Registration

```
POST /api/v1/auth/sign-up
Content-Type: application/json

Request:
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "password_confirm": "SecurePassword123!",
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+84912345678" (optional)
}

Response (201 Created):
{
  "success": true,
  "message": "Sign up successful. Please verify your email.",
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "is_email_verified": false
  }
}

Error (400 Bad Request):
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "email": ["Email already exists"],
    "password": ["Password is too weak"]
  }
}
```

#### 4.2.2 Email Verification

```
POST /api/v1/auth/verify-email
Content-Type: application/json

Request:
{
  "token": "verification_token_from_email"
}

Response (200 OK):
{
  "success": true,
  "message": "Email verified successfully"
}

Error (400 Bad Request):
{
  "success": false,
  "message": "Invalid or expired token"
}
```

#### 4.2.3 User Login

```
POST /api/v1/auth/login
Content-Type: application/json

Request:
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}

Response (200 OK):
{
  "success": true,
  "message": "Login successful",
  "data": {
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe"
    },
    "tokens": {
      "access_token": "eyJhbGc...",
      "refresh_token": "eyJhbGc...",
      "token_type": "Bearer",
      "expires_in": 3600
    }
  }
}

Error (401 Unauthorized):
{
  "success": false,
  "message": "Invalid email or password"
}
```

#### 4.2.4 Google OAuth Callback

```
GET /api/v1/auth/google/callback?code=auth_code&state=state_token

Response (200 OK with redirect):
{
  "success": true,
  "message": "Google authentication successful",
  "data": {
    "user": { ... },
    "tokens": { ... },
    "is_new_user": false
  }
}
```

#### 4.2.5 Logout

```
POST /api/v1/auth/logout
Authorization: Bearer {access_token}
Content-Type: application/json

Request:
{
  "revoke_all_sessions": false  // if true, logout all devices
}

Response (200 OK):
{
  "success": true,
  "message": "Logged out successfully"
}

Error (401 Unauthorized):
{
  "success": false,
  "message": "Authentication required"
}
```

#### 4.2.6 Password Reset Request

```
POST /api/v1/auth/password-reset/request
Content-Type: application/json

Request:
{
  "email": "user@example.com"
}

Response (200 OK):
{
  "success": true,
  "message": "Password reset email sent"
}

Note: Always return success even if email not found (security)
```

#### 4.2.7 Password Reset Confirmation

```
POST /api/v1/auth/password-reset/confirm
Content-Type: application/json

Request:
{
  "token": "reset_token_from_email",
  "new_password": "NewPassword456!",
  "password_confirm": "NewPassword456!"
}

Response (200 OK):
{
  "success": true,
  "message": "Password reset successfully"
}

Error (400 Bad Request):
{
  "success": false,
  "message": "Invalid or expired token"
}
```

#### 4.2.8 OTP Verification

```
POST /api/v1/auth/verify-otp
Authorization: Bearer {access_token}
Content-Type: application/json

Request:
{
  "otp_code": "123456",
  "otp_type": "email_verification"
}

Response (200 OK):
{
  "success": true,
  "message": "OTP verified successfully"
}

Error (400 Bad Request):
{
  "success": false,
  "message": "Invalid OTP code"
}
```

#### 4.2.9 Token Refresh

```
POST /api/v1/auth/refresh
Content-Type: application/json

Request:
{
  "refresh_token": "eyJhbGc..."
}

Response (200 OK):
{
  "success": true,
  "data": {
    "access_token": "eyJhbGc...",
    "token_type": "Bearer",
    "expires_in": 3600
  }
}

Error (401 Unauthorized):
{
  "success": false,
  "message": "Invalid refresh token"
}
```

### 4.3 Error Response Format

```json
{
  "success": false,
  "message": "Human-readable error message",
  "error_code": "VALIDATION_ERROR",
  "errors": {
    "field_name": ["error message 1", "error message 2"]
  },
  "timestamp": "2026-05-01T12:00:00Z"
}
```

### 4.4 Status Codes Used

- **200 OK**: Success
- **201 Created**: Resource created
- **400 Bad Request**: Validation error
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Insufficient permissions
- **404 Not Found**: Resource not found
- **429 Too Many Requests**: Rate limited
- **500 Internal Server Error**: Server error

---

## 5. DEPENDENCIES & SETUP

### 5.1 Core Dependencies

```
Django==4.2.29
djangorestframework==3.14.0
djangorestframework-simplejwt==5.3.2
django-cors-headers==4.3.1
django-environ==0.11.2
psycopg2-binary==2.9.9
PyJWT==2.8.1
```

### 5.2 Security Dependencies

```
django-ratelimit==4.1.0
cryptography==41.0.7
bcrypt==4.1.1
email-validator==2.1.0
```

### 5.3 OAuth Dependencies

```
google-auth==2.25.2
google-auth-httplib2==0.2.0
google-auth-oauthlib==1.2.0
requests==2.31.0
```

### 5.4 Development Dependencies

```
pytest==7.4.3
pytest-django==4.7.0
pytest-cov==4.1.0
factory-boy==3.3.0
faker==22.0.0
```

### 5.5 Email Delivery

```
django-anymail==10.2
# Or: celery==5.3.4 (for async email)
```

### 5.6 Monitoring & Logging

```
sentry-sdk==1.38.0
python-logging-loki==0.3.2  (optional for logs)
```

### 5.7 Installation Steps

```bash
# 1. Install base dependencies
pip install -r requirements.txt

# 2. Update settings.py (see Section 7)

# 3. Create auth app
python manage.py startapp auth apps/auth

# 4. Create PostgreSQL database
createdb rag_be_db

# 5. Run migrations
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser
```

---

## 6. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1)

**Goal**: Database setup, models, migrations, basic infrastructure

- [x] Setup PostgreSQL connection
- [x] Create auth app in apps/auth
- [x] Define User model (extend AbstractUser)
- [x] Define OTPToken model
- [x] Define PasswordResetToken model
- [x] Define EmailVerificationToken model
- [x] Define AuthSession model
- [x] Run migrations
- [x] Create serializers base structure
- [x] Setup DRF (Django REST Framework)
- [ ] **Deliverable**: Database ready, models tested, migrations in place

### Phase 2: Authentication Core (Week 2)

**Goal**: Email/password auth, token generation, validation

- [ ] Implement TokenService (JWT generation/validation)
- [ ] Implement PasswordHashingService (bcrypt)
- [ ] Implement EmailVerificationService
- [ ] Create SignUpView + SignUpSerializer
- [ ] Create LoginView + LoginSerializer
- [ ] Create VerifyEmailView + VerifyEmailSerializer
- [ ] Create LogoutView
- [ ] Setup custom authentication middleware
- [ ] Rate limiting middleware
- [ ] **Deliverable**: Email/password auth working, email verification flow

### Phase 3: Password Reset & OTP (Week 2-3)

**Goal**: Self-service password reset, OTP verification

- [ ] Implement PasswordResetService
- [ ] Implement OTPService (generate 6-digit codes)
- [ ] Create PasswordResetRequestView
- [ ] Create PasswordResetConfirmView
- [ ] Create OTPVerifyView
- [ ] Setup email template system
- [ ] **Deliverable**: Password reset working, OTP verification functional

### Phase 4: OAuth Integration (Week 3-4)

**Goal**: Google OAuth 2.0 login

- [ ] Setup Google OAuth credentials
- [ ] Implement GoogleOAuthService
- [ ] Create GoogleCallbackView
- [ ] Handle first-time Google login (auto-create account)
- [ ] Link existing email accounts to Google
- [ ] **Deliverable**: Google login working end-to-end

### Phase 5: Session Management (Week 4)

**Goal**: Token refresh, session revocation, device tracking

- [ ] Implement TokenRefreshView
- [ ] Implement session tracking (device info, IP)
- [ ] Create LogoutAllDevicesView
- [ ] Implement token revocation
- [ ] **Deliverable**: Multi-device session management

### Phase 6: Testing & Security Hardening (Week 5)

**Goal**: Comprehensive testing, security audit, performance optimization

- [ ] Unit tests (80%+ coverage)
- [ ] Integration tests
- [ ] E2E tests (signup → verify → login flow)
- [ ] Security review (OWASP top 10)
- [ ] Rate limit testing
- [ ] Load testing
- [ ] Documentation
- [ ] **Deliverable**: Production-ready auth system

### Phase 7: Deployment & Monitoring (Week 6)

**Goal**: Deploy to staging/production, setup monitoring

- [ ] Environment configuration (staging, production)
- [ ] Database backup strategy
- [ ] Sentry integration for error tracking
- [ ] Logging setup (Loki optional)
- [ ] CI/CD pipeline
- [ ] **Deliverable**: Deployed, monitored, production-ready

---

## 7. DJANGO SETTINGS CONFIGURATION

### 7.1 Installed Apps Update

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',
    'django_ratelimit',

    # Local apps
    'apps.auth',  # Our authentication app
]
```

### 7.2 Database Configuration

```python
import os
from pathlib import Path
import environ

env = environ.Env()
environ.Env.read_env()

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME', default='rag_be_db'),
        'USER': env('DB_USER', default='postgres'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,
        'ATOMIC_REQUESTS': True,  # Transaction per request
    }
}
```

### 7.3 JWT Configuration

```python
from datetime import timedelta

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': env('SECRET_KEY'),
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}
```

### 7.4 Middleware & CORS

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.auth.middleware.RateLimitMiddleware',
    'apps.auth.middleware.TokenAuthenticationMiddleware',
]

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=['http://localhost:3000'])
```

### 7.5 Email Configuration

```python
# Using Anymail with AWS SES / SendGrid
EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'  # or ses, mailgun, etc.
ANYMAIL = {
    'SENDGRID_API_KEY': env('SENDGRID_API_KEY'),
}

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@ragapp.com')
```

### 7.6 Security Settings

```python
# Environment-based
DEBUG = env.bool('DEBUG', default=False)
SECRET_KEY = env('SECRET_KEY')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost'])

# HTTPS & Security
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Rate Limiting
RATELIMIT_ENABLE = True
AUTH_RATE_LIMITS = {
    'login': '5/h',
    'sign_up': '10/h',
    'password_reset': '3/h',
    'verify_email': '10/h',
}
```

### 7.7 Logging

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/auth.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.auth': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
    },
}
```

---

## 8. SECURITY CONSIDERATIONS

### 8.1 Authentication Security

- ✅ **Password Hashing**: Use Django's `make_password()` (PBKDF2 by default, can upgrade to bcrypt)
- ✅ **JWT Tokens**: Signed with SECRET_KEY, short-lived (1 hour access, 7 days refresh)
- ✅ **Token Rotation**: Refresh tokens rotated on use
- ✅ **Token Revocation**: AuthSession tracks active sessions, can revoke any time
- ✅ **Session Timeout**: Automatic cleanup of expired tokens (celery task)

### 8.2 Input Validation & Sanitization

- ✅ **Email Validation**: RFC 5322 compliant using `email-validator`
- ✅ **Password Requirements**:
  - Minimum 8 characters
  - Uppercase + lowercase + numbers + special chars
  - Not common passwords (Django validator)
  - Not similar to user attributes
- ✅ **Rate Limiting**: Per-IP rate limits on sensitive endpoints
- ✅ **XSS Prevention**: DRF serializers auto-escape, no HTML in responses

### 8.3 CSRF & CORS

- ✅ **CSRF Token**: Django middleware enforces CSRF
- ✅ **CORS**: Whitelist frontend URLs only
- ✅ **Same-Site Cookies**: `SameSite=Lax` on refresh tokens
- ✅ **Credential Cookies**: Only with explicit CORS allowance

### 8.4 OAuth Security

- ✅ **State Parameter**: Prevent CSRF on OAuth callback
- ✅ **Redirect URI Validation**: Whitelist allowed URLs
- ✅ **Token Storage**: Access token in memory, refresh token secure HTTP-only cookie
- ✅ **Token Expiration**: Validate token expiry before use

### 8.5 Secret Management

- ❌ **NO hardcoded secrets** in code
- ✅ **All secrets in environment variables**:
  - `SECRET_KEY`
  - `DB_PASSWORD`
  - `SENDGRID_API_KEY`
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
  - `JWT_SECRET_KEY` (optional, can use SECRET_KEY)

### 8.6 Database Security

- ✅ **SQL Injection**: Django ORM prevents via parameterized queries
- ✅ **Row-Level Security**: User can only access their own data
- ✅ **Audit Logging**: Track password changes, token generation
- ✅ **Encryption at Rest**: PostgreSQL encryption (pgcrypto extension optional)

### 8.7 Brute Force Protection

- ✅ **Rate Limiting**: 5 login attempts / hour per IP
- ✅ **Account Lockout**: Optional, after 10 failed attempts
- ✅ **Failed Attempt Tracking**: Log failed logins for audit
- ✅ **Progressive Delays**: Increase response time after failures

### 8.8 Logging & Monitoring

- ✅ **Audit Logs**: Log all auth events (login, logout, password change)
- ✅ **Error Tracking**: Sentry integration for exceptions
- ✅ **Alerting**: Alert on suspicious activity (many failed attempts, unusual locations)
- ✅ **Data Minimization**: Don't log passwords or tokens

---

## 9. TESTING STRATEGY

### 9.1 Test Structure

```
apps/auth/tests/
├── __init__.py
├── conftest.py              # pytest fixtures
├── test_models.py           # Model tests (200-300 lines)
├── test_serializers.py      # Serializer validation tests
├── test_views.py            # API endpoint tests (400-500 lines)
├── test_services.py         # Business logic tests
├── test_integrations.py     # End-to-end user flows
├── factories.py             # Test data factories
└── fixtures/
    ├── users.json
    └── tokens.json
```

### 9.2 Test Coverage Target

- **Total Coverage**: 80%+
- **Models**: 100% (all field validations)
- **Serializers**: 85% (all validators)
- **Views**: 80% (happy path + error cases)
- **Services**: 90% (all business logic paths)

### 9.3 Test Types & Examples

#### 9.3.1 Unit Tests - Models

```python
# test_models.py
import pytest
from django.contrib.auth.hashers import check_password
from apps.auth.models import User, OTPToken

@pytest.mark.django_db
class TestUserModel:
    def test_user_creation_with_email(self):
        user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!'
        )
        assert user.email == 'test@example.com'
        assert user.check_password('TestPass123!')

    def test_user_password_hashed(self):
        user = User.objects.create_user(
            email='test@example.com',
            password='TestPass123!'
        )
        assert not user.password == 'TestPass123!'
        assert check_password('TestPass123!', user.password)

    def test_user_email_normalized(self):
        user = User.objects.create_user(
            email='TEST@EXAMPLE.COM',
            password='TestPass123!'
        )
        assert user.email == 'test@example.com'

@pytest.mark.django_db
class TestOTPToken:
    def test_otp_token_expires(self):
        from datetime import timedelta
        from django.utils import timezone
        user = User.objects.create_user(email='test@example.com')
        otp = OTPToken.objects.create(
            user=user,
            code='123456',
            type='email_verification',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        assert otp.is_expired()
```

#### 9.3.2 Integration Tests - Views

```python
# test_views.py
import pytest
from django.test import Client
from apps.auth.models import User
import json

@pytest.fixture
def api_client():
    return Client()

@pytest.mark.django_db
class TestSignUpView:
    def test_sign_up_success(self, api_client):
        response = api_client.post('/api/v1/auth/sign-up', {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'John',
            'last_name': 'Doe',
        }, content_type='application/json')

        assert response.status_code == 201
        assert User.objects.count() == 1
        user = User.objects.first()
        assert user.email == 'newuser@example.com'
        assert not user.is_email_verified

    def test_sign_up_duplicate_email(self, api_client):
        User.objects.create_user(email='test@example.com')
        response = api_client.post('/api/v1/auth/sign-up', {
            'email': 'test@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
        }, content_type='application/json')

        assert response.status_code == 400
        assert 'email' in response.json()['errors']

    def test_sign_up_weak_password(self, api_client):
        response = api_client.post('/api/v1/auth/sign-up', {
            'email': 'test@example.com',
            'password': '123',
        }, content_type='application/json')

        assert response.status_code == 400
        assert 'password' in response.json()['errors']

@pytest.mark.django_db
class TestLoginView:
    def test_login_success(self, api_client):
        User.objects.create_user(
            email='test@example.com',
            password='SecurePass123!'
        )
        response = api_client.post('/api/v1/auth/login', {
            'email': 'test@example.com',
            'password': 'SecurePass123!',
        }, content_type='application/json')

        assert response.status_code == 200
        data = response.json()['data']
        assert 'access_token' in data['tokens']
        assert 'refresh_token' in data['tokens']

    def test_login_invalid_credentials(self, api_client):
        User.objects.create_user(
            email='test@example.com',
            password='SecurePass123!'
        )
        response = api_client.post('/api/v1/auth/login', {
            'email': 'test@example.com',
            'password': 'WrongPassword',
        }, content_type='application/json')

        assert response.status_code == 401

    def test_login_rate_limited(self, api_client):
        for i in range(6):
            response = api_client.post('/api/v1/auth/login', {
                'email': f'test{i}@example.com',
                'password': 'wrong',
            }, content_type='application/json')

        assert response.status_code == 429
```

#### 9.3.3 E2E Tests - Full User Flow

```python
# test_integrations.py
import pytest
from django.test import Client
from apps.auth.models import User, EmailVerificationToken

@pytest.mark.django_db
class TestSignUpToLoginFlow:
    def test_complete_signup_verify_login_flow(self):
        client = Client()

        # 1. Sign up
        signup_response = client.post('/api/v1/auth/sign-up', {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'John',
        }, content_type='application/json')

        assert signup_response.status_code == 201
        user = User.objects.get(email='newuser@example.com')

        # 2. Verify email
        email_token = EmailVerificationToken.objects.get(user=user)
        verify_response = client.post('/api/v1/auth/verify-email', {
            'token': email_token.token,
        }, content_type='application/json')

        assert verify_response.status_code == 200
        user.refresh_from_db()
        assert user.is_email_verified

        # 3. Login
        login_response = client.post('/api/v1/auth/login', {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
        }, content_type='application/json')

        assert login_response.status_code == 200
        tokens = login_response.json()['data']['tokens']
        assert tokens['access_token']
        assert tokens['refresh_token']

        # 4. Logout
        logout_response = client.post('/api/v1/auth/logout',
            HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}",
            content_type='application/json'
        )
        assert logout_response.status_code == 200
```

### 9.4 Test Data & Fixtures

```python
# factories.py
import factory
from faker import Faker
from apps.auth.models import User

fake = Faker()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    password = factory.PostGenerationMethodCall('set_password', 'TestPass123!')
    is_email_verified = True
    is_active = True
```

### 9.5 Running Tests

```bash
# Run all tests
pytest apps/auth/tests/ -v

# Run with coverage
pytest apps/auth/tests/ --cov=apps.auth --cov-report=html

# Run specific test
pytest apps/auth/tests/test_views.py::TestLoginView::test_login_success -v

# Run and stop on first failure
pytest apps/auth/tests/ -x

# Run with print statements
pytest apps/auth/tests/ -s
```

---

## 10. ENVIRONMENT VARIABLES

### 10.1 `.env` Template

```bash
# Django Core
SECRET_KEY=your-super-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com

# Database - PostgreSQL
DB_ENGINE=django.db.backends.postgresql
DB_NAME=rag_be_db
DB_USER=postgres
DB_PASSWORD=your-secure-password
DB_HOST=localhost
DB_PORT=5432

# Email
EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
SENDGRID_API_KEY=your-sendgrid-key
DEFAULT_FROM_EMAIL=noreply@ragapp.com

# JWT
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ACCESS_TOKEN_LIFETIME=3600  # 1 hour in seconds
JWT_REFRESH_TOKEN_LIFETIME=604800  # 7 days in seconds

# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001

# Rate Limiting
RATELIMIT_ENABLE=True
AUTH_RATE_LIMITS_LOGIN=5/h
AUTH_RATE_LIMITS_SIGNUP=10/h
AUTH_RATE_LIMITS_PASSWORD_RESET=3/h

# Sentry (Error Tracking)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# OTP Settings
OTP_LENGTH=6
OTP_EXPIRATION_MINUTES=10

# Email Verification Token
EMAIL_VERIFICATION_TOKEN_EXPIRATION_HOURS=24

# Password Reset Token
PASSWORD_RESET_TOKEN_EXPIRATION_HOURS=24
```

### 10.2 Environment Variables by Environment

#### Development (.env.local)

```bash
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_HOST=localhost
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend  # Console output
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

#### Staging (.env.staging)

```bash
DEBUG=False
ALLOWED_HOSTS=staging.ragapp.com
DB_HOST=db.staging.ragapp.com
EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
GOOGLE_OAUTH_REDIRECT_URI=https://staging.ragapp.com/api/v1/auth/google/callback
CORS_ALLOWED_ORIGINS=https://staging.ragapp.com
SECURE_SSL_REDIRECT=True
```

#### Production (.env.production)

```bash
DEBUG=False
ALLOWED_HOSTS=ragapp.com,www.ragapp.com
DB_HOST=db-prod.ragapp.com
DB_NAME=rag_be_prod
EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
GOOGLE_OAUTH_REDIRECT_URI=https://ragapp.com/api/v1/auth/google/callback
CORS_ALLOWED_ORIGINS=https://ragapp.com,https://www.ragapp.com
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

---

## 11. QUICK START CHECKLIST

### Pre-Implementation

- [ ] Review this plan with team
- [ ] Setup PostgreSQL locally
- [ ] Gather Google OAuth credentials
- [ ] Decide on email service (SendGrid, AWS SES, etc.)
- [ ] Create `.env.example` from Section 10.1

### Implementation Phases

- [ ] **Phase 1**: Database & Models (3-4 days)
- [ ] **Phase 2**: Auth Core (3-4 days)
- [ ] **Phase 3**: Password Reset & OTP (2-3 days)
- [ ] **Phase 4**: OAuth (2-3 days)
- [ ] **Phase 5**: Sessions (1-2 days)
- [ ] **Phase 6**: Testing & Security (3-4 days)
- [ ] **Phase 7**: Deployment (2-3 days)

### Validation

- [ ] All tests pass (80%+ coverage)
- [ ] No hardcoded secrets
- [ ] Security review completed
- [ ] Rate limiting working
- [ ] Email notifications working
- [ ] Google OAuth working
- [ ] Token refresh working
- [ ] Logout revokes session

---

## 12. REFERENCES & LINKS

### Django Authentication

- [Django User Model](https://docs.djangoproject.com/en/4.2/ref/contrib/auth/#user-model)
- [Django Permissions](https://docs.djangoproject.com/en/4.2/topics/auth/default/#permissions-and-authorization)
- [Custom User Model](https://docs.djangoproject.com/en/4.2/topics/auth/customizing/#substituting-a-custom-user-model)

### DRF & JWT

- [DRF Authentication](https://www.django-rest-framework.org/api-guide/authentication/)
- [djangorestframework-simplejwt](https://github.com/jpadilla/django-rest-framework-simplejwt)
- [JWT Best Practices](https://tools.ietf.org/html/rfc7519)

### OAuth 2.0

- [Google OAuth 2.0 Flow](https://developers.google.com/identity/protocols/oauth2)
- [OAuth 2.0 Security](https://datatracker.ietf.org/doc/html/rfc6749)

### Security

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Password Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
- [Secure Password Hashing](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

### Email Services

- [SendGrid API](https://docs.sendgrid.com/)
- [Django Anymail](https://anymail.readthedocs.io/)

### Testing

- [pytest-django](https://pytest-django.readthedocs.io/)
- [Factory Boy](https://factoryboy.readthedocs.io/)

---

## 13. KNOWN CHALLENGES & SOLUTIONS

| Challenge                   | Impact                  | Solution                                         |
| --------------------------- | ----------------------- | ------------------------------------------------ |
| Email delivery delays       | Poor UX                 | Use SendGrid with webhooks to track delivery     |
| Token expiration timing     | Auth failures           | Use 1h access + 7d refresh pattern with rotation |
| OAuth state parameter       | CSRF on OAuth           | Store state in cache, validate immediately       |
| Rate limit false positives  | Blocks legitimate users | Allow whitelist IPs, user appeals process        |
| Database connection pooling | Connection exhaustion   | Use pgbouncer, Django CONN_MAX_AGE=600           |
| Expired tokens in rotation  | Stale sessions          | Celery task to cleanup tokens daily              |
| Password reset token leaks  | Account takeover        | Token sent via secure link, single-use, expiring |
| OTP brute force             | Account takeover        | Rate limit OTP attempts, max 5 per hour          |

---

## CONCLUSION

This plan provides a **production-ready authentication system** for Django RAG backend following:

- ✅ TDD methodology
- ✅ Security best practices
- ✅ RESTful API design
- ✅ Clear implementation phases
- ✅ Comprehensive testing strategy
- ✅ Environment-based configuration

**Next Step**: Start Phase 1 with database setup and model creation. Review plan with team and adjust timeline as needed.
