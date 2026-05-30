import pytest

from apps.auth.models import EmailVerificationToken, OTPToken, PasswordResetToken, TwoFactorLoginChallenge, User
from apps.auth.serializers import (
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    LoginSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer,
    SignUpSerializer,
)


@pytest.mark.django_db
def test_signup_serializer_creates_lowercase_email_user_and_verification_token(monkeypatch):
    monkeypatch.setattr('apps.auth.serializers.validate_email', lambda value: value)

    serializer = SignUpSerializer(data={
        'email': 'NEWUSER@example.com',
        'first_name': 'New',
        'last_name': 'User',
        'password': 'StrongPass1!',
        'password_confirm': 'StrongPass1!',
    })

    assert serializer.is_valid(), serializer.errors
    user = serializer.save()

    assert user.email == 'newuser@example.com'
    assert user.check_password('StrongPass1!')
    assert EmailVerificationToken.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_signup_serializer_rejects_duplicate_email(user, monkeypatch):
    monkeypatch.setattr('apps.auth.serializers.validate_email', lambda value: value)

    serializer = SignUpSerializer(data={
        'email': user.email.upper(),
        'password': 'StrongPass1!',
        'password_confirm': 'StrongPass1!',
    })

    assert serializer.is_valid() is False
    assert 'email' in serializer.errors


@pytest.mark.django_db
def test_login_serializer_rejects_locked_account(user):
    user.is_active = False
    user.save(update_fields=['is_active'])

    serializer = LoginSerializer(data={'email': user.email, 'password': 'StrongPass1!'})

    assert serializer.is_valid() is False
    assert 'locked' in str(serializer.errors).lower()


@pytest.mark.django_db
def test_otp_verify_serializer_requires_login_challenge(user):
    otp = OTPToken.create_otp(user, purpose='login_2fa')
    serializer = OTPVerifySerializer(data={
        'email': user.email,
        'otp': otp.otp,
        'purpose': 'login_2fa',
    })

    assert serializer.is_valid() is False
    assert 'challenge' in str(serializer.errors).lower()


@pytest.mark.django_db
def test_otp_verify_serializer_accepts_valid_login_challenge(user):
    challenge = TwoFactorLoginChallenge.create_challenge(user)
    serializer = OTPVerifySerializer(data={
        'email': user.email,
        'otp': challenge.otp_token.otp,
        'purpose': 'login_2fa',
        'challenge_token': challenge.token,
    })

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data['login_challenge'] == challenge


@pytest.mark.django_db
def test_password_reset_confirm_rejects_mismatched_passwords(user):
    token = PasswordResetToken.create_token(user)
    serializer = PasswordResetConfirmSerializer(data={
        'token': token.token,
        'password': 'StrongPass1!',
        'password_confirm': 'OtherPass1!',
    })

    assert serializer.is_valid() is False
    assert 'password_confirm' in serializer.errors


@pytest.mark.django_db
def test_email_verification_serializer_accepts_active_token(user):
    token = EmailVerificationToken.create_token(user)
    serializer = EmailVerificationSerializer(data={'token': token.token})

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_change_password_serializer_requires_current_password_for_password_user(rf_request):
    serializer = ChangePasswordSerializer(
        data={'new_password': 'NewStrong1!', 'new_password_confirm': 'NewStrong1!'},
        context={'request': rf_request},
    )

    assert serializer.is_valid() is False
    assert 'old_password' in serializer.errors


@pytest.mark.django_db
def test_user_serializer_role_helpers(db):
    admin = User.objects.create_user(username='admin@example.com', email='admin@example.com', password='StrongPass1!', is_staff=True)
    superadmin = User.objects.create_superuser(username='root@example.com', email='root@example.com', password='StrongPass1!')

    from apps.auth.serializers import UserSerializer

    assert UserSerializer(admin).data['role'] == 'admin'
    assert UserSerializer(superadmin).data['role'] == 'superadmin'
