from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import User, EmailVerificationToken, OTPToken, PasswordResetToken, AuthSession


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin interface for User model."""
    
    list_display = (
        'email', 'get_full_name', 'is_email_verified', 'is_active',
        'last_login_at', 'created_at'
    )
    list_filter = ('is_email_verified', 'is_active', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'google_id')
    ordering = ('-created_at',)
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Email & Verification', {
            'fields': ('is_email_verified',)
        }),
        ('OAuth', {
            'fields': ('google_id',),
            'classes': ('collapse',)
        }),
        ('Profile', {
            'fields': ('phone_number', 'avatar_url', 'bio'),
            'classes': ('collapse',)
        }),
        ('Activity', {
            'fields': ('last_login_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('last_login_at', 'created_at', 'updated_at')


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Admin interface for EmailVerificationToken model."""
    
    list_display = (
        'user', 'get_status', 'created_at', 'expires_at', 'verified_at'
    )
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'created_at', 'verified_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Token', {
            'fields': ('token', 'is_used')
        }),
        ('Expiry', {
            'fields': ('created_at', 'expires_at', 'verified_at')
        }),
    )
    
    def get_status(self, obj):
        """Display verification status with color."""
        if obj.is_used:
            return format_html('<span style="color: green;">✓ Verified</span>')
        elif obj.is_valid():
            return format_html('<span style="color: orange;">⏳ Pending</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')
    
    get_status.short_description = 'Status'


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    """Admin interface for OTPToken model."""
    
    list_display = (
        'user', 'purpose', 'get_status', 'attempts',
        'created_at', 'expires_at'
    )
    list_filter = ('purpose', 'is_used', 'created_at')
    search_fields = ('user__email', 'otp')
    ordering = ('-created_at',)
    readonly_fields = ('otp', 'created_at')
    
    fieldsets = (
        ('User & Purpose', {
            'fields': ('user', 'purpose')
        }),
        ('OTP', {
            'fields': ('otp', 'is_used')
        }),
        ('Attempts', {
            'fields': ('attempts',)
        }),
        ('Expiry', {
            'fields': ('created_at', 'expires_at', 'verified_at')
        }),
    )
    
    def get_status(self, obj):
        """Display OTP status with color."""
        if obj.is_used:
            return format_html('<span style="color: green;">✓ Used</span>')
        elif obj.is_valid():
            return format_html('<span style="color: orange;">⏳ Valid</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')
    
    get_status.short_description = 'Status'


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin interface for PasswordResetToken model."""
    
    list_display = (
        'user', 'get_status', 'created_at', 'expires_at', 'reset_at'
    )
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__email', 'token')
    ordering = ('-created_at',)
    readonly_fields = ('token', 'created_at', 'reset_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Token', {
            'fields': ('token', 'is_used')
        }),
        ('Expiry', {
            'fields': ('created_at', 'expires_at', 'reset_at')
        }),
    )
    
    def get_status(self, obj):
        """Display reset status with color."""
        if obj.is_used:
            return format_html('<span style="color: green;">✓ Used</span>')
        elif obj.is_valid():
            return format_html('<span style="color: orange;">⏳ Valid</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')
    
    get_status.short_description = 'Status'


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    """Admin interface for AuthSession model."""
    
    list_display = (
        'user', 'device_name', 'ip_address', 'get_status',
        'created_at', 'last_activity_at'
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'device_name', 'ip_address')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'last_activity_at', 'revoked_at')
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Device Info', {
            'fields': ('device_name', 'ip_address', 'user_agent')
        }),
        ('Session', {
            'fields': ('refresh_token', 'access_token_jti', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_activity_at', 'revoked_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_status(self, obj):
        """Display session status with color."""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Active</span>')
        else:
            return format_html('<span style="color: red;">✗ Revoked</span>')
    
    get_status.short_description = 'Status'
