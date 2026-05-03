import uuid
import secrets
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


class User(AbstractUser):
    """Extended User model with email verification and OAuth support."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    
    # OAuth fields
    google_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    
    # Profile info
    avatar_url = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['google_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.email} ({self.get_full_name()})"
    
    def update_last_login(self):
        """Update last login timestamp."""
        self.last_login_at = timezone.now()
        self.save(update_fields=['last_login_at'])


class EmailVerificationToken(models.Model):
    """Token for email verification during sign up."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='email_verification_token')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Email Verification Token'
        verbose_name_plural = 'Email Verification Tokens'
    
    def __str__(self):
        return f"Email verification for {self.user.email}"
    
    @classmethod
    def create_token(cls, user):
        """Create a new email verification token."""
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(
            hours=settings.EMAIL_VERIFICATION_EXPIRY_HOURS
        )
        
        # Delete previous token if exists
        cls.objects.filter(user=user).delete()
        
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if token is still valid."""
        return not self.is_used and timezone.now() < self.expires_at
    
    def mark_as_verified(self):
        """Mark token as used and verified."""
        self.is_used = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_used', 'verified_at'])


class OTPToken(models.Model):
    """OTP token for 2FA and password reset verification."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_tokens')
    otp = models.CharField(max_length=6)  # 6-digit OTP
    purpose = models.CharField(
        max_length=20,
        choices=[
            ('login_2fa', '2FA Login'),
            ('password_reset', 'Password Reset'),
            ('signup', 'Signup Verification'),
        ],
        default='login_2fa'
    )
    
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'OTP Token'
        verbose_name_plural = 'OTP Tokens'
        indexes = [
            models.Index(fields=['user', 'otp']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"OTP for {self.user.email} ({self.purpose})"
    
    @classmethod
    def create_otp(cls, user, purpose='login_2fa'):
        """Create a new OTP token."""
        otp = secrets.randbelow(1000000)  # 0-999999
        otp_str = str(otp).zfill(6)  # Pad with zeros
        
        expires_at = timezone.now() + timedelta(
            minutes=settings.OTP_EXPIRY_MINUTES
        )
        
        return cls.objects.create(
            user=user,
            otp=otp_str,
            purpose=purpose,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if OTP is still valid."""
        return (
            not self.is_used and
            self.attempts < settings.OTP_MAX_ATTEMPTS and
            timezone.now() < self.expires_at
        )
    
    def verify_otp(self, otp_input):
        """Verify OTP input."""
        self.attempts += 1
        self.save(update_fields=['attempts'])
        
        if not self.is_valid():
            return False
        
        if self.otp != otp_input:
            return False
        
        self.is_used = True
        self.verified_at = timezone.now()
        self.save(update_fields=['is_used', 'verified_at'])
        return True


class PasswordResetToken(models.Model):
    """Token for password reset flow."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    reset_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'
    
    def __str__(self):
        return f"Password reset for {self.user.email}"
    
    @classmethod
    def create_token(cls, user):
        """Create a new password reset token."""
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(
            hours=settings.PASSWORD_RESET_EXPIRY_HOURS
        )
        
        return cls.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
    
    def is_valid(self):
        """Check if token is still valid."""
        return not self.is_used and timezone.now() < self.expires_at
    
    def mark_as_used(self):
        """Mark token as used."""
        self.is_used = True
        self.reset_at = timezone.now()
        self.save(update_fields=['is_used', 'reset_at'])


class AuthSession(models.Model):
    """Track authentication sessions for multi-device logout support."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_sessions')
    
    refresh_token = models.TextField(unique=True, db_index=True)
    access_token_jti = models.CharField(max_length=255, blank=True)
    
    device_name = models.CharField(max_length=255, blank=True)  # e.g., "Chrome on Windows"
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField()
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name = 'Auth Session'
        verbose_name_plural = 'Auth Sessions'
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Session for {self.user.email} - {self.device_name}"
    
    def revoke(self):
        """Revoke this session."""
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=['is_active', 'revoked_at'])
    
    @classmethod
    def cleanup_expired(cls):
        """Remove sessions older than 30 days."""
        cutoff_date = timezone.now() - timedelta(days=30)
        cls.objects.filter(created_at__lt=cutoff_date, is_active=False).delete()
