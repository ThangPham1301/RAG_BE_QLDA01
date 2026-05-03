# Authentication System Documentation

This document describes the authentication system implementation for RAG Backend.

## Overview

The authentication system provides comprehensive user management with multiple authentication methods:

- **Email/Password Authentication** - Traditional sign up and login
- **Google OAuth 2.0** - Sign up and login with Google
- **OTP Verification** - Two-factor authentication and password reset
- **Session Management** - Multi-device session tracking
- **Email Verification** - Required before first login

## Architecture

```
apps/auth/
├── models.py           # User and token models
├── serializers.py      # Data validation and transformation
├── views.py            # API endpoints
├── urls.py             # URL routing
├── admin.py            # Django admin interface
├── tests.py            # Test suite
└── templates/
    └── auth/emails/    # Email templates
```

## Database Models

### User

Extended AbstractUser model with:

- UUID primary key
- Email-based authentication
- Email verification status
- Google OAuth ID
- Profile information (avatar, bio, phone)
- Last login tracking

### EmailVerificationToken

Single-use tokens for email verification during signup:

- 24-hour expiry
- Automatically deleted after use
- One per user at a time

### OTPToken

One-Time Passwords for 2FA and password reset:

- 6-digit codes
- Configurable expiry (default 10 minutes)
- Max 5 attempt limit
- Two purposes: login_2fa, password_reset

### PasswordResetToken

Tokens for secure password reset:

- Single-use
- 24-hour expiry
- Revokes all sessions when used

### AuthSession

Multi-device session tracking:

- IP address and User-Agent logging
- Per-device logout capability
- Revocation tracking

## API Endpoints

### Public Endpoints (No Authentication Required)

#### Sign Up

```
POST /api/auth/signup
Content-Type: application/json

{
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "password": "SecurePassword123!",
    "password_confirm": "SecurePassword123!"
}

Response: 201 Created
{
    "message": "Sign up successful. Please check your email to verify your account.",
    "user": { ... }
}
```

#### Verify Email

```
POST /api/auth/verify-email
Content-Type: application/json

{
    "token": "verification-token-from-email"
}

Response: 200 OK
{
    "message": "Email verified successfully. You can now log in."
}
```

#### Login (Email/Password)

```
POST /api/auth/login
Content-Type: application/json

{
    "email": "user@example.com",
    "password": "SecurePassword123!"
}

Response: 200 OK
{
    "message": "Login successful",
    "user": { ... },
    "tokens": {
        "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    },
    "session_id": "uuid"
}
```

#### Request OTP

```
POST /api/auth/request-otp
Content-Type: application/json

{
    "email": "user@example.com",
    "purpose": "password_reset"  // or "login_2fa"
}

Response: 200 OK
{
    "message": "OTP sent to user@example.com"
}
```

#### Verify OTP

```
POST /api/auth/verify-otp
Content-Type: application/json

{
    "email": "user@example.com",
    "otp": "123456",
    "purpose": "password_reset"  // or "login_2fa"
}

Response: 200 OK
{
    "message": "OTP verified. You can now reset your password.",
    "reset_token": "token-for-password-reset"
}
```

#### Password Reset - Request

```
POST /api/auth/password-reset/request
Content-Type: application/json

{
    "email": "user@example.com"
}

Response: 200 OK
{
    "message": "If an account exists with that email, you will receive an OTP to reset your password."
}
```

#### Password Reset - Confirm

```
POST /api/auth/password-reset/confirm
Content-Type: application/json

{
    "token": "reset-token",
    "password": "NewPassword123!",
    "password_confirm": "NewPassword123!"
}

Response: 200 OK
{
    "message": "Password reset successful. All sessions have been revoked. Please log in again."
}
```

#### Google OAuth Callback

```
POST /api/auth/google/callback
Content-Type: application/json

{
    "id_token": "google-id-token",
    "access_token": "google-access-token"  // optional
}

Response: 200 OK
{
    "message": "Google login successful",
    "user": { ... },
    "tokens": { ... },
    "session_id": "uuid"
}
```

#### Token Refresh

```
POST /api/auth/token/refresh
Content-Type: application/json

{
    "refresh": "refresh-token-from-login"
}

Response: 200 OK
{
    "access": "new-access-token",
    "refresh": "new-refresh-token"  // if rotation enabled
}
```

### Protected Endpoints (Authentication Required)

All protected endpoints require:

```
Authorization: Bearer <access-token>
```

#### Get Current User

```
GET /api/auth/me

Response: 200 OK
{
    "id": "uuid",
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "is_email_verified": true,
    ...
}
```

#### Update Profile

```
PUT /api/auth/profile
Content-Type: application/json

{
    "first_name": "Jane",
    "bio": "Updated bio",
    "avatar_url": "https://..."
}

Response: 200 OK
{ ... updated user data ... }
```

#### Change Password

```
POST /api/auth/change-password
Content-Type: application/json

{
    "old_password": "CurrentPassword123!",
    "new_password": "NewPassword123!",
    "new_password_confirm": "NewPassword123!"
}

Response: 200 OK
{
    "message": "Password changed successfully. Please log in again."
}
```

#### Get Active Sessions

```
GET /api/auth/sessions

Response: 200 OK
[
    {
        "id": "uuid",
        "device_name": "Chrome on Windows",
        "ip_address": "192.168.1.1",
        "is_active": true,
        "created_at": "2024-05-01T10:00:00Z",
        "last_activity_at": "2024-05-01T10:30:00Z"
    },
    ...
]
```

#### Logout (All Sessions)

```
POST /api/auth/logout

Response: 200 OK
{
    "message": "Logged out successfully. All sessions have been revoked."
}
```

#### Logout Device (Specific Session)

```
POST /api/auth/logout-device
Content-Type: application/json

{
    "session_id": "uuid"
}

Response: 200 OK
{
    "message": "Logged out from device successfully."
}
```

## Security Features

### Password Security

- Minimum 8 characters
- Must not be similar to username/email
- Must not be entirely numeric
- Common password validation
- Bcrypt hashing (Django default)

### Token Security

- JWT tokens with HS256 algorithm
- 1-hour access token lifetime
- 7-day refresh token lifetime
- Token rotation on refresh
- Automatic blacklisting of old refresh tokens

### OTP Security

- 6-digit codes
- 10-minute expiry (configurable)
- Maximum 5 attempt limit
- Revoked after successful verification

### Session Security

- IP address logging
- User-Agent logging
- Per-device logout capability
- All sessions revoked on password reset/change
- 30-day cleanup of inactive sessions

### Rate Limiting

- 5 sign-up attempts per hour per IP
- 10 login attempts per hour per IP
- 5 password reset requests per hour per IP
- 10 OTP attempts per hour per IP

### Email Verification

- Mandatory before first login
- 24-hour token expiry
- Single-use tokens
- Sent via configured email backend

## Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```
DB_NAME=rag_be_db
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key

GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### 3. Create Database

```bash
createdb rag_be_db  # PostgreSQL
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Collect Static Files (Production)

```bash
python manage.py collectstatic
```

## Running Tests

### Run All Tests

```bash
python manage.py test apps.auth
```

### Run Specific Test Class

```bash
python manage.py test apps.auth.tests.SignUpAPITestCase
```

### Run with Coverage

```bash
coverage run --source='apps.auth' manage.py test apps.auth
coverage report
coverage html
```

## Management Commands

### Clean Up Expired Tokens

```bash
# Default: delete sessions older than 30 days
python manage.py cleanup_tokens

# Custom days
python manage.py cleanup_tokens --days=60
```

## Google OAuth Setup

### 1. Create Google OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google+ API
4. Go to Credentials → Create OAuth 2.0 Client ID
5. Select "Web application"
6. Add authorized redirect URIs:
   - `http://localhost:8000/api/auth/google/callback`
   - `https://yourdomain.com/api/auth/google/callback`

### 2. Update Environment Variables

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
```

## Email Configuration

### Using Gmail (Development)

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

To generate Gmail app password:

1. Enable 2-factor authentication on Google Account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Select Mail and Windows Computer
4. Copy the generated password

### Using SendGrid (Production)

```python
# Update settings.py
EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'
ANYMAIL = {
    'SENDGRID_API_KEY': env('SENDGRID_API_KEY'),
}
```

## Troubleshooting

### "Invalid email or password"

- Verify email exists and is verified (check `is_email_verified`)
- Check password is correct
- Try password reset if forgotten

### "Email not verified"

- Check user's email for verification link
- Request new verification email (sign up again)
- Check spam/junk folder

### "Invalid or expired OTP"

- OTP may have expired (10 minutes default)
- OTP may have been already used
- Max attempts (5) may have been exceeded
- Request new OTP

### "Invalid Google token"

- Verify Google credentials are correct
- Check ID token is still valid
- Token may have expired

### PostgreSQL Connection Error

- Verify database is running
- Check DB_HOST, DB_USER, DB_PASSWORD in .env
- Verify database exists: `psql -l`

## Performance Optimization

### Database Indexes

- Email field indexed for fast lookups
- Google ID indexed for OAuth lookups
- Token fields indexed for fast verification

### Caching

- In-memory cache for rate limiting
- JWT tokens cached in browser

### Query Optimization

- `select_related` and `prefetch_related` used where applicable
- Pagination on session list endpoint

## Future Enhancements

1. **Two-Factor Authentication (2FA)**
   - Authenticator apps (TOTP)
   - SMS-based OTP

2. **Social Login**
   - GitHub OAuth
   - Facebook OAuth
   - LinkedIn OAuth

3. **Advanced Security**
   - Passwordless login (magic links)
   - FIDO2/WebAuthn support
   - Risk-based authentication

4. **Account Recovery**
   - Account deletion with grace period
   - Email change verification
   - Phone number verification

5. **Monitoring & Analytics**
   - Login attempt tracking
   - Failed login alerts
   - Session analytics

## Support & Debugging

For detailed logs, enable DEBUG mode in settings.py and check:

- Django logs: `python manage.py runserver`
- Email logs: Check `email.log` file
- Database logs: Check PostgreSQL logs

## References

- [Django Authentication](https://docs.djangoproject.com/en/4.2/topics/auth/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [SimpleJWT](https://django-rest-framework-simplejwt.readthedocs.io/)
- [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
