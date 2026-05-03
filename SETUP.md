# RAG Backend - Setup Guide

Complete step-by-step guide to set up the RAG Backend with authentication system.

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- pip or conda
- Virtual environment (venv, conda, or poetry)

## Step 1: Clone & Setup Project

```bash
# Navigate to project directory
cd RAG_BE_QLDA01

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

## Step 2: Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt

# Verify installation
pip list
```

## Step 3: Configure PostgreSQL

### Windows (Using PostgreSQL installer)

```bash
# Start PostgreSQL service
# Services → PostgreSQL Server → Start

# Create database
createdb rag_be_db

# Verify database was created
psql -l
```

### macOS (Using Homebrew)

```bash
# Install PostgreSQL
brew install postgresql

# Start PostgreSQL
brew services start postgresql

# Create database
createdb rag_be_db
```

### Linux (Ubuntu/Debian)

```bash
# Install PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# Start PostgreSQL
sudo systemctl start postgresql

# Create database
sudo -u postgres createdb rag_be_db
```

## Step 4: Configure Environment Variables

```bash
# Copy example env file to .env
cp .env.example .env

# Edit .env with your configuration
# At minimum, update:
# - SECRET_KEY (generate a new one)
# - DB_PASSWORD
# - GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (optional for local dev)
```

### Generate SECRET_KEY

```python
# In Python shell:
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

Then copy the output and paste into .env as `SECRET_KEY`.

## Step 5: Database Migrations

```bash
# Navigate to project root
cd RAG_BE_QLDA01

# Create migrations for auth app
python manage.py makemigrations auth

# Apply migrations
python manage.py migrate

# Verify migrations were applied
python manage.py showmigrations auth
```

## Step 6: Create Superuser

```bash
# Create admin user
python manage.py createsuperuser

# You'll be prompted for:
# - Username: admin
# - Email: admin@example.com
# - Password: (create a strong password)
```

## Step 7: Run Development Server

```bash
# Start Django development server
python manage.py runserver

# Server will be available at: http://localhost:8000
# Admin panel: http://localhost:8000/admin
```

## Step 8: Test Authentication Endpoints

### Using curl:

```bash
# Test sign up
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "first_name": "Test",
    "last_name": "User",
    "password": "TestPassword123!",
    "password_confirm": "TestPassword123!"
  }'

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "TestPassword123!"
  }'
```

### Using Python requests:

```python
import requests

BASE_URL = "http://localhost:8000/api/auth"

# Sign up
response = requests.post(f"{BASE_URL}/signup", json={
    "email": "testuser@example.com",
    "first_name": "Test",
    "last_name": "User",
    "password": "TestPassword123!",
    "password_confirm": "TestPassword123!"
})
print(response.json())
```

### Using Postman/Insomnia:

1. Import the provided Postman collection
2. Set base URL to `http://localhost:8000`
3. Start testing endpoints

## Step 9: Run Tests

```bash
# Run all auth tests
python manage.py test apps.auth

# Run specific test class
python manage.py test apps.auth.tests.SignUpAPITestCase

# Run with verbose output
python manage.py test apps.auth -v 2

# Run with coverage
coverage run --source='apps.auth' manage.py test apps.auth
coverage report
coverage html  # Generate HTML report in htmlcov/
```

## Step 10: Setup Email (Optional)

### For Gmail:

1. Enable 2-Factor Authentication on your Google Account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Select Mail and Windows Computer
4. Copy the generated 16-character password
5. Update `.env`:
   ```
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=paste-16-char-password
   ```

### For SendGrid:

1. Create a SendGrid account
2. Generate an API key
3. Update `.env`:
   ```
   EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
   SENDGRID_API_KEY=your-sendgrid-api-key
   ```

## Step 11: Setup Google OAuth (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google+ API
4. Go to Credentials → OAuth Consent Screen
   - Select "External"
   - Add scopes: openid, email, profile
5. Go to Credentials → Create OAuth 2.0 Client ID
   - Select "Web application"
   - Add URIs:
     - `http://localhost:8000`
     - `http://localhost:3000` (frontend)
   - Authorized redirect URIs:
     - `http://localhost:8000/api/auth/google/callback`
6. Copy Client ID and Secret
7. Update `.env`:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```

## Common Issues & Solutions

### Issue: Database connection error

```
django.db.utils.OperationalError: could not connect to server
```

**Solution:**

- Verify PostgreSQL is running
- Check DB_HOST, DB_USER, DB_PASSWORD in .env
- Verify database exists: `psql -l`

### Issue: Secret key error

```
django.core.exceptions.ImproperlyConfigured: The SECRET_KEY setting must not be empty
```

**Solution:**

- Generate and add SECRET_KEY to .env
- Verify .env file exists in project root

### Issue: CORS error in frontend

```
Access to XMLHttpRequest blocked by CORS policy
```

**Solution:**

- Update CORS_ALLOWED_ORIGINS in .env
- Include your frontend URL: `http://localhost:5173`

### Issue: Email not sending

```
SMTPAuthenticationError: Application-specific password required
```

**Solution:**

- Use app-specific password (not account password)
- For Gmail, enable 2FA and generate app password
- Check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD

## Development Workflow

### During Development:

```bash
# Keep terminal 1 running the server
python manage.py runserver

# In terminal 2, run tests as you code
python manage.py test apps.auth --keepdb

# Watch for changes and auto-reload with watchmedo (optional)
pip install watchdog
watchmedo auto-reload -d . -p '*.py' -- python manage.py runserver
```

### Before Committing:

```bash
# Run all tests
python manage.py test apps.auth

# Check code with linters
flake8 apps/auth

# Generate coverage report
coverage run --source='apps.auth' manage.py test apps.auth
coverage report

# Migration check
python manage.py makemigrations --check
```

### Using Django Admin:

```
URL: http://localhost:8000/admin
Username: admin (from Step 6)
Password: (from Step 6)

You can now:
- View users
- Manage tokens
- View sessions
- Review email verification status
```

## Production Checklist

Before deploying to production:

- [ ] Change DEBUG = False
- [ ] Generate new SECRET_KEY and JWT_SECRET_KEY
- [ ] Use strong database password
- [ ] Configure PostgreSQL with backups
- [ ] Setup email service (SendGrid/Mailgun)
- [ ] Setup Google OAuth with production URIs
- [ ] Configure HTTPS/SSL
- [ ] Setup environment variables on hosting platform
- [ ] Run migrations on production database
- [ ] Create superuser on production
- [ ] Setup monitoring (Sentry)
- [ ] Configure logging
- [ ] Test all API endpoints
- [ ] Run security checks

## File Structure

```
RAG_BE_QLDA01/
├── .env                        # Environment variables (create from .env.example)
├── .env.example               # Template for environment variables
├── requirements.txt           # Python dependencies
├── manage.py                  # Django management script
├── RAG_BE/                    # Project settings
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── apps/
    └── auth/                  # Authentication app
        ├── models.py          # Database models
        ├── views.py           # API endpoints
        ├── serializers.py     # Data validation
        ├── urls.py            # URL routing
        ├── admin.py           # Django admin
        ├── tests.py           # Test suite
        ├── apps.py            # App configuration
        ├── README.md          # Auth documentation
        ├── templates/
        │   └── auth/emails/   # Email templates
        └── management/
            └── commands/
                └── cleanup_tokens.py  # Cleanup utility
```

## Next Steps

1. **Test all endpoints** - Use Postman/curl to verify functionality
2. **Setup frontend** - Configure React app to use these endpoints
3. **Implement frontend** - Create sign up, login, password reset UI
4. **Add more features** - Implement additional auth methods if needed
5. **Deploy** - Move to production following the checklist

## Support

For issues or questions:

1. Check the [Auth README](apps/auth/README.md)
2. Review test cases in `apps/auth/tests.py`
3. Check Django/DRF documentation
4. Review error logs in terminal

## Quick Commands Reference

```bash
# Database
python manage.py migrate                          # Apply migrations
python manage.py makemigrations                   # Create migrations
python manage.py showmigrations                   # Show migration status

# Testing
python manage.py test apps.auth                   # Run all tests
python manage.py test apps.auth --keepdb         # Keep test database
coverage run ... && coverage report               # With coverage

# Admin
python manage.py createsuperuser                  # Create admin user
python manage.py changepassword username          # Change password

# Utilities
python manage.py cleanup_tokens                   # Clean expired tokens
python manage.py dbshell                          # SQL shell
python manage.py shell                            # Python shell

# Server
python manage.py runserver                        # Start dev server
python manage.py runserver 0.0.0.0:8000          # Listen on all IPs
```

---

**You're all set!** Start developing with the authentication system. 🚀
