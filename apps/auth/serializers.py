import re
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from email_validator import validate_email, EmailNotValidError

from .models import User, OTPToken, PasswordResetToken, EmailVerificationToken, AuthSession


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'username',
            'phone_number', 'avatar_url', 'bio', 'is_email_verified',
            'created_at', 'updated_at', 'last_login_at'
        ]
        read_only_fields = [
            'id', 'is_email_verified', 'created_at', 'updated_at', 'last_login_at'
        ]


class SignUpSerializer(serializers.ModelSerializer):
    """Serializer for user sign up."""
    
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        help_text='Password must be at least 8 characters'
    )
    password_confirm = serializers.CharField(
        write_only=True,
        help_text='Password confirmation'
    )
    email = serializers.EmailField()
    
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password', 'password_confirm']
    
    def validate_email(self, value):
        """Validate email format and uniqueness."""
        try:
            validate_email(value)
        except EmailNotValidError as e:
            raise serializers.ValidationError(str(e))
        
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('Email already registered')
        
        return value.lower()
    
    def validate_password(self, value):
        """Validate password strength."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        return value
    
    def validate(self, data):
        """Validate password match."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match'
            })
        
        return data
    
    def create(self, validated_data):
        """Create user and send verification email."""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Create user with email as username initially
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['email'],
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        
        # Create email verification token
        EmailVerificationToken.create_token(user)
        
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for login with email and password."""
    
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        """Authenticate user."""
        user = User.objects.filter(email=data['email']).first()
        
        if not user:
            raise serializers.ValidationError('Invalid email or password')
        
        if not user.is_email_verified:
            raise serializers.ValidationError('Email not verified. Please check your email.')
        
        if not user.check_password(data['password']):
            raise serializers.ValidationError('Invalid email or password')
        
        data['user'] = user
        return data


class OTPRequestSerializer(serializers.Serializer):
    """Serializer for OTP request (login 2FA or password reset)."""
    
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(
        choices=['login_2fa', 'password_reset', 'signup'],
        default='login_2fa'
    )
    
    def validate_email(self, value):
        """Check if email exists."""
        if not User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('User not found')
        return value.lower()


class OTPVerifySerializer(serializers.Serializer):
    """Serializer for OTP verification."""
    
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    purpose = serializers.ChoiceField(
        choices=['login_2fa', 'password_reset', 'signup'],
        default='login_2fa'
    )
    
    def validate_email(self, value):
        """Check if email exists."""
        if not User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('User not found')
        return value.lower()
    
    def validate_otp(self, value):
        """Validate OTP format."""
        if not value.isdigit():
            raise serializers.ValidationError('OTP must be numeric')
        return value
    
    def validate(self, data):
        """Validate OTP exists and is valid."""
        user = User.objects.get(email=data['email'])
        otp_token = OTPToken.objects.filter(
            user=user,
            otp=data['otp'],
            purpose=data['purpose']
        ).last()
        
        if not otp_token or not otp_token.is_valid():
            raise serializers.ValidationError('Invalid or expired OTP')
        
        data['otp_token'] = otp_token
        return data


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer for password reset request."""
    
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Check if email exists."""
        if not User.objects.filter(email=value.lower()).exists():
            # Don't reveal if email exists for security
            return value.lower()
        return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer for password reset confirmation."""
    
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    def validate_password(self, value):
        """Validate password strength."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
    
    def validate(self, data):
        """Validate password match and token."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match'
            })
        
        # Check if token exists and is valid
        token = PasswordResetToken.objects.filter(
            token=data['token'],
            is_used=False
        ).first()
        
        if not token or not token.is_valid():
            raise serializers.ValidationError('Invalid or expired reset token')
        
        data['token_obj'] = token
        return data


class EmailVerificationSerializer(serializers.Serializer):
    """Serializer for email verification."""
    
    token = serializers.CharField()
    
    def validate_token(self, value):
        """Check if token exists and is valid."""
        token = EmailVerificationToken.objects.filter(token=value).first()
        
        if not token or not token.is_valid():
            raise serializers.ValidationError('Invalid or expired verification token')
        
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password."""
    
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate_new_password(self, value):
        """Validate new password strength."""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value
    
    def validate(self, data):
        """Validate new password match and old password correct."""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': 'Passwords do not match'
            })
        
        user = self.context['request'].user
        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({
                'old_password': 'Old password is incorrect'
            })
        
        return data


class AuthSessionSerializer(serializers.ModelSerializer):
    """Serializer for Auth Session."""
    
    class Meta:
        model = AuthSession
        fields = [
            'id', 'device_name', 'ip_address', 'is_active',
            'created_at', 'last_activity_at', 'revoked_at'
        ]
        read_only_fields = ['id', 'created_at', 'last_activity_at', 'revoked_at']


class TokenRefreshSerializer(serializers.Serializer):
    """Serializer for token refresh."""
    
    refresh = serializers.CharField()
    
    def validate_refresh(self, value):
        """Validate refresh token."""
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            RefreshToken(value)
        except Exception:
            raise serializers.ValidationError('Invalid refresh token')
        return value


class GoogleOAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth."""
    
    id_token = serializers.CharField()
    access_token = serializers.CharField(required=False)
