from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
MEDIA_ROOT = BASE_DIR / 'test_media'  # noqa: F405
LOGGING_CONFIG = None
PASSWORD_RESET_EXPIRY_HOURS = 24
EMAIL_VERIFICATION_EXPIRY_HOURS = 24
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
AUTH_PASSWORD_VALIDATORS = []
