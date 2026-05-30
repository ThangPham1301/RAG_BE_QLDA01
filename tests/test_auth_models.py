from datetime import timedelta

import pytest
from django.utils import timezone

from apps.auth.models import EmailVerificationToken, OTPToken, TwoFactorLoginChallenge


@pytest.mark.django_db
def test_email_verification_token_replaces_existing_token(user):
    first = EmailVerificationToken.create_token(user)
    second = EmailVerificationToken.create_token(user)

    assert first.token != second.token
    assert EmailVerificationToken.objects.filter(user=user).count() == 1
    assert second.is_valid() is True


@pytest.mark.django_db
def test_email_verification_token_mark_as_verified(user):
    token = EmailVerificationToken.create_token(user)

    token.mark_as_verified()
    token.refresh_from_db()

    assert token.is_used is True
    assert token.verified_at is not None
    assert token.is_valid() is False


@pytest.mark.django_db
def test_otp_verify_tracks_attempts_and_marks_success(user):
    otp = OTPToken.create_otp(user, purpose='password_reset')

    assert otp.verify_otp('000000') is False
    otp.refresh_from_db()
    assert otp.attempts == 1
    assert otp.is_used is False

    assert otp.verify_otp(otp.otp) is True
    otp.refresh_from_db()
    assert otp.attempts == 2
    assert otp.is_used is True
    assert otp.verified_at is not None


@pytest.mark.django_db
def test_two_factor_challenge_invalid_when_expired(user):
    challenge = TwoFactorLoginChallenge.create_challenge(user)
    challenge.expires_at = timezone.now() - timedelta(minutes=1)
    challenge.save(update_fields=['expires_at'])

    assert challenge.is_valid() is False
