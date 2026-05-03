import pytest
from django.test import TestCase, Client
from django.core import mail
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

from .models import (
    EmailVerificationToken, OTPToken, PasswordResetToken, AuthSession
)

User = get_user_model()


class UserModelTestCase(TestCase):
    """Test User model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!'
        )
    
    def test_user_creation(self):
        """Test user creation."""
        self.assertEqual(self.user.email, 'test@example.com')
        self.assertTrue(self.user.check_password('TestPassword123!'))
    
    def test_update_last_login(self):
        """Test update_last_login method."""
        self.assertIsNone(self.user.last_login_at)
        self.user.update_last_login()
        self.assertIsNotNone(self.user.last_login_at)


class EmailVerificationTokenTestCase(TestCase):
    """Test EmailVerificationToken model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!'
        )
    
    def test_token_creation(self):
        """Test token creation."""
        token = EmailVerificationToken.create_token(self.user)
        self.assertIsNotNone(token.token)
        self.assertFalse(token.is_used)
    
    def test_token_validity(self):
        """Test token validity check."""
        token = EmailVerificationToken.create_token(self.user)
        self.assertTrue(token.is_valid())
    
    def test_mark_as_verified(self):
        """Test marking token as verified."""
        token = EmailVerificationToken.create_token(self.user)
        token.mark_as_verified()
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.verified_at)


class OTPTokenTestCase(TestCase):
    """Test OTPToken model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!'
        )
    
    def test_otp_creation(self):
        """Test OTP creation."""
        otp = OTPToken.create_otp(self.user)
        self.assertIsNotNone(otp.otp)
        self.assertEqual(len(otp.otp), 6)
        self.assertFalse(otp.is_used)
    
    def test_otp_validity(self):
        """Test OTP validity check."""
        otp = OTPToken.create_otp(self.user)
        self.assertTrue(otp.is_valid())
    
    def test_otp_expiry(self):
        """Test OTP expiry."""
        otp = OTPToken.create_otp(self.user)
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save()
        self.assertFalse(otp.is_valid())
    
    def test_otp_max_attempts(self):
        """Test OTP max attempts."""
        otp = OTPToken.create_otp(self.user)
        otp.attempts = 5
        otp.save()
        self.assertFalse(otp.is_valid())


class SignUpAPITestCase(APITestCase):
    """Test sign up API endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.signup_url = '/api/auth/signup'
    
    def test_signup_success(self):
        """Test successful sign up."""
        data = {
            'email': 'newuser@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'password': 'TestPassword123!',
            'password_confirm': 'TestPassword123!'
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
        user = User.objects.get(email='newuser@example.com')
        otp_token = OTPToken.objects.filter(user=user, purpose='signup').first()
        self.assertIsNotNone(otp_token)
        self.assertTrue(any(otp_token.otp in message.body for message in mail.outbox))
    
    def test_signup_password_mismatch(self):
        """Test sign up with password mismatch."""
        data = {
            'email': 'newuser@example.com',
            'password': 'TestPassword123!',
            'password_confirm': 'DifferentPassword!'
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_signup_weak_password(self):
        """Test sign up with weak password."""
        data = {
            'email': 'newuser@example.com',
            'password': '123',
            'password_confirm': '123'
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_signup_duplicate_email(self):
        """Test sign up with duplicate email."""
        User.objects.create_user(
            email='existing@example.com',
            username='existing',
            password='TestPassword123!'
        )
        
        data = {
            'email': 'existing@example.com',
            'password': 'TestPassword123!',
            'password_confirm': 'TestPassword123!'
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EmailVerificationAPITestCase(APITestCase):
    """Test email verification API endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.verify_url = '/api/auth/verify-email'
        
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!'
        )
        self.token = EmailVerificationToken.create_token(self.user)
    
    def test_verify_email_success(self):
        """Test successful email verification."""
        data = {'token': self.token.token}
        response = self.client.post(self.verify_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
    
    def test_verify_email_invalid_token(self):
        """Test email verification with invalid token."""
        data = {'token': 'invalid-token'}
        response = self.client.post(self.verify_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginAPITestCase(APITestCase):
    """Test login API endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.login_url = '/api/auth/login'
        
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!',
            is_email_verified=True
        )
    
    def test_login_success(self):
        """Test successful login."""
        data = {
            'email': 'test@example.com',
            'password': 'TestPassword123!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
    
    def test_login_invalid_password(self):
        """Test login with invalid password."""
        data = {
            'email': 'test@example.com',
            'password': 'WrongPassword!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_login_unverified_email(self):
        """Test login with unverified email."""
        user = User.objects.create_user(
            email='unverified@example.com',
            username='unverified',
            password='TestPassword123!',
            is_email_verified=False
        )
        
        data = {
            'email': 'unverified@example.com',
            'password': 'TestPassword123!'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OTPAPITestCase(APITestCase):
    """Test OTP API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.request_otp_url = '/api/auth/request-otp'
        self.verify_otp_url = '/api/auth/verify-otp'
        
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!',
            is_email_verified=True
        )
    
    def test_request_otp_success(self):
        """Test successful OTP request."""
        data = {
            'email': 'test@example.com',
            'purpose': 'password_reset'
        }
        response = self.client.post(self.request_otp_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_verify_otp_success(self):
        """Test successful OTP verification."""
        otp = OTPToken.create_otp(self.user, purpose='password_reset')
        
        data = {
            'email': 'test@example.com',
            'otp': otp.otp,
            'purpose': 'password_reset'
        }
        response = self.client.post(self.verify_otp_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_verify_otp_invalid(self):
        """Test OTP verification with invalid OTP."""
        data = {
            'email': 'test@example.com',
            'otp': '000000',
            'purpose': 'password_reset'
        }
        response = self.client.post(self.verify_otp_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_signup_otp_marks_email_verified(self):
        """Test signup OTP verification marks email as verified."""
        user = User.objects.create_user(
            email='signup@example.com',
            username='signupuser',
            password='TestPassword123!',
            is_email_verified=False
        )
        otp = OTPToken.create_otp(user, purpose='signup')
        data = {
            'email': 'signup@example.com',
            'otp': otp.otp,
            'purpose': 'signup'
        }
        response = self.client.post(self.verify_otp_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)


class PasswordResetAPITestCase(APITestCase):
    """Test password reset API endpoints."""
    
    def setUp(self):
        self.client = APIClient()
        self.reset_request_url = '/api/auth/password-reset/request'
        self.reset_confirm_url = '/api/auth/password-reset/confirm'
        
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!',
            is_email_verified=True
        )
    
    def test_password_reset_request(self):
        """Test password reset request."""
        data = {'email': 'test@example.com'}
        response = self.client.post(self.reset_request_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        otp_token = OTPToken.objects.filter(user=self.user, purpose='password_reset').first()
        self.assertIsNotNone(otp_token)
        self.assertTrue(any(otp_token.otp in message.body for message in mail.outbox))
    
    def test_password_reset_confirm_success(self):
        """Test successful password reset."""
        token = PasswordResetToken.create_token(self.user)
        
        data = {
            'token': token.token,
            'password': 'NewPassword123!',
            'password_confirm': 'NewPassword123!'
        }
        response = self.client.post(self.reset_confirm_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify password was changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPassword123!'))


class LogoutAPITestCase(APITestCase):
    """Test logout API endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.logout_url = '/api/auth/logout'
        
        self.user = User.objects.create_user(
            email='test@example.com',
            username='testuser',
            password='TestPassword123!',
            is_email_verified=True
        )
        
        # Login to get token
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(self.user)
        self.token = str(refresh.access_token)
    
    def test_logout_success(self):
        """Test successful logout."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_logout_without_auth(self):
        """Test logout without authentication."""
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
