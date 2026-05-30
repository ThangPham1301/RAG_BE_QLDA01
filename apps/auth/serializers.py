import re
from rest_framework import serializers
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from email_validator import validate_email, EmailNotValidError

from .models import (
    User, OTPToken, PasswordResetToken, EmailVerificationToken, AuthSession,
    TwoFactorLoginChallenge
)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
<<<<<<< HEAD
=======

>>>>>>> 77d0dce (feat(auth): add two-factor authentication support and admin user management)
    role = serializers.SerializerMethodField()
    has_usable_password = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'username',
            'phone_number', 'avatar_url', 'bio', 'is_email_verified',
<<<<<<< HEAD
<<<<<<< HEAD
            'is_staff', 'is_superuser', 'role',
            'created_at', 'updated_at', 'last_login_at'
        ]
        read_only_fields = [
            'id', 'is_email_verified', 'is_staff', 'is_superuser', 'role',
=======
            'two_factor_enabled', 'is_staff', 'is_superuser', 'role',
            'created_at', 'updated_at', 'last_login_at'
        ]
        read_only_fields = [
            'id', 'is_email_verified', 'two_factor_enabled', 'is_staff', 'is_superuser', 'role',
>>>>>>> 77d0dce (feat(auth): add two-factor authentication support and admin user management)
            'created_at', 'updated_at', 'last_login_at'
=======
            'is_two_factor_enabled', 'is_staff', 'is_superuser', 'role',
            'has_usable_password', 'created_at', 'updated_at', 'last_login_at'
        ]
        read_only_fields = [
            'id', 'is_email_verified', 'is_two_factor_enabled', 'is_staff', 'is_superuser', 'role',
            'has_usable_password', 'created_at', 'updated_at', 'last_login_at'
>>>>>>> 427532e (feat(auth): implement two-factor authentication and token versioning)
        ]

    def get_role(self, obj):
<<<<<<< HEAD
        return 'admin' if obj.is_staff or obj.is_superuser else 'user'
=======
        if obj.is_superuser or obj.is_staff:
            return 'admin'
        return 'user'


class AdminUserSerializer(UserSerializer):
    """Expanded user payload for admin user management."""

    groups = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            'is_active', 'groups', 'date_joined'
        ]
        read_only_fields = UserSerializer.Meta.read_only_fields + [
            'date_joined'
        ]

    def get_groups(self, obj):
        return [
            {'id': group.id, 'name': group.name}
            for group in obj.groups.all().order_by('name')
        ]


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Django permission metadata."""

    label = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ['id', 'codename', 'name', 'label']

    def get_label(self, obj):
        return f'{obj.content_type.app_label}.{obj.codename}'


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Django auth groups and assigned permissions."""

    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions']

    def get_permissions(self, obj):
        return PermissionSerializer(obj.permissions.all().order_by('content_type__app_label', 'codename'), many=True).data
>>>>>>> 77d0dce (feat(auth): add two-factor authentication support and admin user management)

    def get_has_usable_password(self, obj):
        return bool(obj.password) and obj.has_usable_password()


class AdminUserSerializer(serializers.ModelSerializer):
    """Compact user data for the in-app admin user management screen."""

    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    active_sessions = serializers.SerializerMethodField()
    team_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 'full_name',
            'phone_number', 'avatar_url', 'bio', 'is_active', 'is_email_verified',
            'is_two_factor_enabled', 'is_staff', 'is_superuser', 'role',
            'groups', 'active_sessions', 'team_count',
            'created_at', 'updated_at', 'last_login_at'
        ]

    def get_role(self, obj):
        if obj.is_superuser:
            return 'superadmin'
        if obj.is_staff:
            return 'admin'
        return 'user'

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_groups(self, obj):
        return [{'id': group.id, 'name': group.name} for group in obj.groups.all()]

    def get_active_sessions(self, obj):
        return obj.auth_sessions.filter(is_active=True).count()

    def get_team_count(self, obj):
        return obj.team_memberships.count()


class AdminUserRoleSerializer(serializers.Serializer):
    """Serializer for admin-driven role changes."""

    role = serializers.ChoiceField(choices=['user', 'admin', 'superadmin'])


class AdminUserStatusSerializer(serializers.Serializer):
    """Serializer for locking or unlocking an account."""

    is_active = serializers.BooleanField()


class AdminResetPasswordSerializer(serializers.Serializer):
    """Serializer for admin password reset."""

    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match'})
        return data


class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source='content_type.app_label', read_only=True)
    model = serializers.CharField(source='content_type.model', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'app_label', 'model']


class GroupSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        source='permissions',
        queryset=Permission.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permission_ids', 'user_count']

    def get_user_count(self, obj):
        return obj.user_set.count()


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
        
        if not user.check_password(data['password']):
            raise serializers.ValidationError('Invalid email or password')

        if not user.is_active:
            raise serializers.ValidationError('This account is locked. Please contact an administrator.')
        
        data['user'] = user
        data['email_not_verified'] = not user.is_email_verified
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
    challenge_token = serializers.CharField(required=False, allow_blank=True)
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

        if data['purpose'] == 'login_2fa':
            challenge_token = data.get('challenge_token')
            if not challenge_token:
                raise serializers.ValidationError('Login challenge is required')

            challenge = TwoFactorLoginChallenge.objects.filter(
                user=user,
                token=challenge_token,
                is_used=False
            ).select_related('otp_token').first()

            if not challenge or not challenge.is_valid():
                raise serializers.ValidationError('Invalid or expired login challenge')

            if challenge.otp_token.otp != data['otp']:
                if not challenge.otp_token.verify_otp(data['otp']):
                    raise serializers.ValidationError('Invalid or expired OTP')

            data['otp_token'] = challenge.otp_token
            data['login_challenge'] = challenge
            return data

        otp_token = OTPToken.objects.filter(
            user=user,
            otp=data['otp'],
            purpose=data['purpose']
        ).last()
        
        if not otp_token or not otp_token.is_valid():
            raise serializers.ValidationError('Invalid or expired OTP')
        
        data['otp_token'] = otp_token
        return data


class TwoFactorToggleSerializer(serializers.Serializer):
    """Serializer for enabling or disabling email OTP two-factor auth."""

    enabled = serializers.BooleanField()


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
    
    old_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
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
        user_has_password = bool(user.password) and user.has_usable_password()
        old_password = data.get('old_password', '')

        if user_has_password and not old_password:
            raise serializers.ValidationError({
                'old_password': 'Old password is required'
            })

        if user_has_password and not user.check_password(old_password):
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
