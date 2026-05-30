import logging
import requests
import re
from urllib.parse import urlencode, urlparse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from cloudinary import uploader
from cloudinary.exceptions import Error as CloudinaryError

from .models import (
    User, EmailVerificationToken, OTPToken, PasswordResetToken, AuthSession,
    TwoFactorLoginChallenge
)
from .serializers import (
    UserSerializer, SignUpSerializer, LoginSerializer, OTPRequestSerializer,
    OTPVerifySerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    EmailVerificationSerializer, ChangePasswordSerializer, AuthSessionSerializer,
    GoogleOAuthSerializer, TwoFactorToggleSerializer, AdminUserSerializer,
    AdminUserRoleSerializer, AdminUserStatusSerializer, AdminResetPasswordSerializer,
    GroupSerializer, PermissionSerializer
)

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when transactional email cannot be delivered."""


def get_frontend_url():
    """Return the configured frontend base URL without a trailing slash."""
    return getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request):
    """Extract user agent from request."""
    return request.META.get('HTTP_USER_AGENT', '')


def create_auth_session(user, request, refresh_token):
    """Create an auth session for the user."""
    return AuthSession.objects.create(
        user=user,
        refresh_token=str(refresh_token),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        device_name=request.META.get('HTTP_USER_AGENT', 'Unknown Device')[:255]
    )


def revoke_all_user_sessions(user):
    """Invalidate all JWTs and tracked sessions for a user."""
    User.objects.filter(pk=user.pk).update(auth_token_version=F('auth_token_version') + 1)
    user.refresh_from_db(fields=['auth_token_version'])

    AuthSession.objects.filter(user=user, is_active=True).update(
        is_active=False,
        revoked_at=timezone.now()
    )
    TwoFactorLoginChallenge.objects.filter(user=user, is_used=False).update(
        is_used=True,
        verified_at=timezone.now()
    )


def issue_auth_response(user, request, message):
    """Create JWT tokens, track the session, and return the login payload."""
    user.update_last_login()
    refresh = RefreshToken.for_user(user)
    refresh['token_version'] = user.auth_token_version
    session = create_auth_session(user, request, refresh)

    return {
        'message': message,
        'user': UserSerializer(user).data,
        'tokens': {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        },
        'session_id': str(session.id)
    }


def send_email(subject, email_to, template_name, context):
    """Helper function to send emails."""
    try:
        html_message = render_to_string(f'auth/emails/{template_name}.html', context)
        plain_message = strip_tags(html_message)
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_to],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email sent to {email_to}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email to {email_to}: {str(e)}")
        raise EmailDeliveryError(str(e)) from e


def send_verification_email(user):
    """Send or resend the account verification email."""
    verification_token = EmailVerificationToken.objects.filter(
        user=user,
        is_used=False,
        expires_at__gt=timezone.now()
    ).first()

    if not verification_token:
        verification_token = EmailVerificationToken.create_token(user)

    email_context = {
        'user_name': user.get_full_name() or user.email,
        'verification_link': f"{get_frontend_url()}/verify-email?token={verification_token.token}"
    }

    send_email(
        subject='Verify Your Email',
        email_to=user.email,
        template_name='verify_email',
        context=email_context
    )


def send_login_2fa_challenge(user):
    """Create a 2FA login challenge and email its OTP."""
    challenge = TwoFactorLoginChallenge.create_challenge(user)
    email_context = {
        'user_name': user.get_full_name() or user.email,
        'otp': challenge.otp_token.otp,
        'expiry_minutes': settings.OTP_EXPIRY_MINUTES
    }

    send_email(
        subject='Your Login Verification Code',
        email_to=user.email,
        template_name='login_otp',
        context=email_context
    )

    return challenge


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/h', method='POST')
def signup_view(request):
    """
    Sign up endpoint.
    POST /api/auth/signup
    """
    serializer = SignUpSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.save()
        try:
            send_verification_email(user)
        except EmailDeliveryError:
            user.delete()
            return Response({
                'detail': 'Unable to send verification email right now. Please try again later.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        return Response({
            'message': 'Sign up successful. Please check your email to verify your account.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


def email_verification_redirect_view(request):
    """
    Backward-compatible GET endpoint for email links that point to the backend.
    Redirects users to the frontend verification page with the same token.
    """
    token = request.GET.get('token', '')
    frontend_url = get_frontend_url()
    redirect_url = f"{frontend_url}/verify-email"
    if token and re.fullmatch(r'[-_A-Za-z0-9]{1,255}', token):
        verified_token = EmailVerificationToken.objects.filter(
            token=token,
            is_used=False,
            expires_at__gt=timezone.now()
        ).values_list('token', flat=True).first()
        if verified_token:
            redirect_url = f"{redirect_url}?{urlencode({'token': verified_token})}"
    allowed_host = urlparse(frontend_url).netloc
    if not url_has_allowed_host_and_scheme(redirect_url, {allowed_host}, require_https=urlparse(frontend_url).scheme == 'https'):
        redirect_url = f"{frontend_url}/verify-email"
    return redirect(redirect_url)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email_view(request):
    """
    Verify email endpoint.
    POST /api/auth/verify-email
    """
    serializer = EmailVerificationSerializer(data=request.data)
    
    if serializer.is_valid():
        token = EmailVerificationToken.objects.get(token=serializer.validated_data['token'])
        token.mark_as_verified()
        
        user = token.user
        user.is_email_verified = True
        user.save()
        
        return Response({
            'message': 'Email verified successfully. You can now log in.'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


def format_serializer_errors(errors):
    """
    Convert serializer errors dict to user-friendly error message.
    Handles nested errors and returns first meaningful error.
    """
    if isinstance(errors, dict):
        for field, messages in errors.items():
            if isinstance(messages, list) and messages:
                return str(messages[0])
            elif messages:
                return str(messages)
    return 'Authentication failed. Please try again.'


def is_admin_user(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def admin_required_response():
    return Response({'detail': 'Admin role is required.'}, status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/h', method='POST')
def login_view(request):
    """
    Login endpoint.
    POST /api/auth/login
    """
    serializer = LoginSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']

        if serializer.validated_data.get('email_not_verified'):
            try:
                send_verification_email(user)
            except EmailDeliveryError:
                return Response({
                    'detail': 'Your email is not verified, and we could not send a verification email right now. Please try again later.',
                    'code': 'email_not_verified'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return Response({
                'detail': 'Your email is not verified. We have sent a verification email. Please check your inbox to confirm your account.',
                'code': 'email_not_verified',
                'email': user.email
            }, status=status.HTTP_403_FORBIDDEN)

        if user.is_two_factor_enabled:
            try:
                challenge = send_login_2fa_challenge(user)
            except EmailDeliveryError:
                return Response({
                    'detail': 'Unable to send login verification code right now. Please try again later.'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

            return Response({
                'message': 'Two-factor verification required. We sent an OTP to your email.',
                'requires_2fa': True,
                'email': user.email,
                'challenge_token': challenge.token,
                'expires_at': challenge.expires_at,
            }, status=status.HTTP_200_OK)

        return Response(
            issue_auth_response(user, request, 'Login successful'),
            status=status.HTTP_200_OK
        )
    
    # Return consistent error format for frontend
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/h', method='POST')
def request_otp_view(request):
    """
    Request OTP for 2FA or password reset.
    POST /api/auth/request-otp
    """
    serializer = OTPRequestSerializer(data=request.data)
    
    if serializer.is_valid():
        user = User.objects.get(email=serializer.validated_data['email'])
        purpose = serializer.validated_data['purpose']

        if purpose == 'login_2fa':
            return Response({
                'detail': 'Login OTP can only be requested after a successful password or Google login step.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create OTP
        otp_token = OTPToken.create_otp(user, purpose)
        
        # Send OTP email
        email_context = {
            'user_name': user.get_full_name() or user.email,
            'otp': otp_token.otp,
            'expiry_minutes': settings.OTP_EXPIRY_MINUTES
        }
        
        if purpose == 'password_reset':
            template = 'password_reset_otp'
            subject = 'Password Reset OTP'
        elif purpose == 'signup':
            template = 'signup_otp'
            subject = 'Verify Your Email - OTP'
        else:
            template = 'login_otp'
            subject = 'Your OTP Code'
        try:
            send_email(
                subject=subject,
                email_to=user.email,
                template_name=template,
                context=email_context
            )
        except EmailDeliveryError:
            return Response({
                'detail': 'Unable to send OTP email right now. Please try again later.'
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        return Response({
            'message': f'OTP sent to {user.email}'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/h', method='POST')
def verify_otp_view(request):
    """
    Verify OTP.
    POST /api/auth/verify-otp
    """
    serializer = OTPVerifySerializer(data=request.data)
    
    if serializer.is_valid():
        otp_token = serializer.validated_data['otp_token']
        user = otp_token.user
        otp_input = serializer.validated_data['otp']

        if not otp_token.verify_otp(otp_input):
            return Response({
                'detail': 'Invalid or expired OTP'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # For password reset, just verify the OTP
        if otp_token.purpose == 'password_reset':
            # Create password reset token
            reset_token = PasswordResetToken.create_token(user)
            return Response({
                'message': 'OTP verified. You can now reset your password.',
                'reset_token': reset_token.token
            }, status=status.HTTP_200_OK)

        if otp_token.purpose == 'signup':
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])
            return Response({
                'message': 'Email verified successfully. You can now log in.'
            }, status=status.HTTP_200_OK)
        
        login_challenge = serializer.validated_data.get('login_challenge')
        if login_challenge:
            login_challenge.mark_as_verified()

        return Response(
            issue_auth_response(user, request, 'OTP verified. Login successful.'),
            status=status.HTTP_200_OK
        )
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='5/h', method='POST')
def password_reset_request_view(request):
    """
    Request password reset (using OTP).
    POST /api/auth/password-reset/request
    """
    serializer = PasswordResetRequestSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            user = User.objects.get(email=serializer.validated_data['email'])
            
            # Create OTP
            otp_token = OTPToken.create_otp(user, purpose='password_reset')
            
            # Send OTP email
            email_context = {
                'user_name': user.get_full_name() or user.email,
                'otp': otp_token.otp,
                'expiry_minutes': settings.OTP_EXPIRY_MINUTES
            }
            
            try:
                send_email(
                    subject='Password Reset Request',
                    email_to=user.email,
                    template_name='password_reset_otp',
                    context=email_context
                )
            except EmailDeliveryError:
                logger.error("Failed to deliver password reset OTP email for user: %s", user.email)
        except User.DoesNotExist:
            pass  # Don't reveal if email exists
        
        return Response({
            'message': 'If an account exists with that email, you will receive an OTP to reset your password.'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm_view(request):
    """
    Confirm password reset with token and new password.
    POST /api/auth/password-reset/confirm
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    
    if serializer.is_valid():
        token_obj = serializer.validated_data['token_obj']
        user = token_obj.user
        
        # Update password
        user.set_password(serializer.validated_data['password'])
        user.save()
        
        # Mark token as used
        token_obj.mark_as_used()
        
        revoke_all_user_sessions(user)
        
        # Send confirmation email
        email_context = {
            'user_name': user.get_full_name() or user.email,
        }
        try:
            send_email(
                subject='Password Reset Successful',
                email_to=user.email,
                template_name='password_reset_success',
                context=email_context
            )
        except EmailDeliveryError:
            logger.error("Failed to deliver password reset success email for user: %s", user.email)
        
        return Response({
            'message': 'Password reset successful. All sessions have been revoked. Please log in again.'
        }, status=status.HTTP_200_OK)
    
    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Logout endpoint - revokes current session.
    POST /api/auth/logout
    """
    user = request.user
    
    # Revoke all active sessions
    AuthSession.objects.filter(user=user, is_active=True).update(
        is_active=False,
        revoked_at=timezone.now()
    )
    
    return Response({
        'message': 'Logged out successfully. All sessions have been revoked.'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_device_view(request):
    """
    Logout from specific device.
    POST /api/auth/logout-device
    """
    session_id = request.data.get('session_id')
    user = request.user
    
    try:
        session = AuthSession.objects.get(id=session_id, user=user)
        session.revoke()
        
        return Response({
            'message': 'Logged out from device successfully.'
        }, status=status.HTTP_200_OK)
    except AuthSession.DoesNotExist:
        return Response({
            'error': 'Session not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sessions_view(request):
    """
    Get all active sessions for current user.
    GET /api/auth/sessions
    """
    user = request.user
    sessions = AuthSession.objects.filter(user=user, is_active=True)
    serializer = AuthSessionSerializer(sessions, many=True)
    
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_users_view(request):
    """List and search users for the in-app admin screen."""
    if not is_admin_user(request.user):
        return admin_required_response()

    search = (request.query_params.get('search') or '').strip()
    role = (request.query_params.get('role') or '').strip()
    status_filter = (request.query_params.get('status') or '').strip()

    users = User.objects.all().prefetch_related('groups').order_by('-created_at')

    if search:
        users = users.filter(
            Q(email__icontains=search)
            | Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    if role == 'admin':
        users = users.filter(is_staff=True, is_superuser=False)
    elif role == 'superadmin':
        users = users.filter(is_superuser=True)
    elif role == 'user':
        users = users.filter(is_staff=False, is_superuser=False)

    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'locked':
        users = users.filter(is_active=False)

    return Response(AdminUserSerializer(users[:200], many=True).data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def admin_user_status_view(request, user_id):
    """Lock or unlock a user account."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    if target.id == request.user.id:
        return Response({'detail': 'You cannot lock your own account.'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = AdminUserStatusSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'detail': format_serializer_errors(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    target.is_active = serializer.validated_data['is_active']
    target.save(update_fields=['is_active'])

    if not target.is_active:
        revoke_all_user_sessions(target)

    return Response(AdminUserSerializer(target).data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def admin_user_role_view(request, user_id):
    """Assign application role for a user."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    if target.id == request.user.id:
        return Response({'detail': 'You cannot change your own role.'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = AdminUserRoleSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'detail': format_serializer_errors(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    role = serializer.validated_data['role']
    if role == 'superadmin' and not request.user.is_superuser:
        return Response({'detail': 'Only a superadmin can grant superadmin role.'}, status=status.HTTP_403_FORBIDDEN)

    if target.is_superuser and not request.user.is_superuser:
        return Response({'detail': 'Only a superadmin can change another superadmin.'}, status=status.HTTP_403_FORBIDDEN)

    target.is_staff = role in ['admin', 'superadmin']
    target.is_superuser = role == 'superadmin'
    target.save(update_fields=['is_staff', 'is_superuser'])
    revoke_all_user_sessions(target)

    return Response(AdminUserSerializer(target).data, status=status.HTTP_200_OK)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def admin_user_groups_view(request, user_id):
    """Assign Django auth groups to a user."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    group_ids = request.data.get('group_ids', [])
    if not isinstance(group_ids, list):
        return Response({'detail': 'group_ids must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

    groups = Group.objects.filter(id__in=group_ids)
    if groups.count() != len(set(group_ids)):
        return Response({'detail': 'One or more groups were not found.'}, status=status.HTTP_400_BAD_REQUEST)

    target.groups.set(groups)
    revoke_all_user_sessions(target)

    return Response(AdminUserSerializer(target).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_user_reset_password_view(request, user_id):
    """Reset a user's password and invalidate every existing session/token."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = AdminResetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({'detail': format_serializer_errors(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    target.set_password(serializer.validated_data['password'])
    target.save(update_fields=['password'])
    revoke_all_user_sessions(target)

    return Response({'message': 'Password reset successfully. All user sessions were revoked.'}, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def admin_user_delete_view(request, user_id):
    """Delete a user account."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    if target.id == request.user.id:
        return Response({'detail': 'You cannot delete your own account.'}, status=status.HTTP_400_BAD_REQUEST)

    if target.is_superuser and not request.user.is_superuser:
        return Response({'detail': 'Only a superadmin can delete another superadmin.'}, status=status.HTTP_403_FORBIDDEN)

    target.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_user_logs_view(request, user_id):
    """Return recent account activity logs for a user."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    logs = []

    for session in target.auth_sessions.order_by('-created_at')[:30]:
        logs.append({
            'id': str(session.id),
            'type': 'session',
            'title': 'Login session created' if session.is_active else 'Session revoked',
            'created_at': session.created_at,
            'metadata': {
                'device': session.device_name,
                'ip_address': session.ip_address,
                'last_activity_at': session.last_activity_at,
                'revoked_at': session.revoked_at,
            }
        })

    for otp in target.otp_tokens.order_by('-created_at')[:30]:
        logs.append({
            'id': str(otp.id),
            'type': 'otp',
            'title': f'OTP generated for {otp.purpose}',
            'created_at': otp.created_at,
            'metadata': {
                'is_used': otp.is_used,
                'attempts': otp.attempts,
                'expires_at': otp.expires_at,
                'verified_at': otp.verified_at,
            }
        })

    for token in target.password_reset_tokens.order_by('-created_at')[:20]:
        logs.append({
            'id': str(token.id),
            'type': 'password_reset',
            'title': 'Password reset token created',
            'created_at': token.created_at,
            'metadata': {
                'is_used': token.is_used,
                'expires_at': token.expires_at,
                'reset_at': token.reset_at,
            }
        })

    logs.sort(key=lambda item: item['created_at'], reverse=True)
    return Response({'user': AdminUserSerializer(target).data, 'logs': logs[:80]}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_permissions_view(request):
    """List permissions available for group assignment."""
    if not is_admin_user(request.user):
        return admin_required_response()

    permissions = Permission.objects.select_related('content_type').order_by(
        'content_type__app_label',
        'content_type__model',
        'codename',
    )
    return Response(PermissionSerializer(permissions, many=True).data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_groups_view(request):
    """List or create user groups."""
    if not is_admin_user(request.user):
        return admin_required_response()

    if request.method == 'GET':
        groups = Group.objects.prefetch_related('permissions').order_by('name')
        return Response(GroupSerializer(groups, many=True).data, status=status.HTTP_200_OK)

    serializer = GroupSerializer(data=request.data)
    if serializer.is_valid():
        group = serializer.save()
        return Response(GroupSerializer(group).data, status=status.HTTP_201_CREATED)

    return Response({'detail': format_serializer_errors(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_group_detail_view(request, group_id):
    """Update or delete a user group."""
    if not is_admin_user(request.user):
        return admin_required_response()

    try:
        group = Group.objects.get(id=group_id)
    except Group.DoesNotExist:
        return Response({'detail': 'Group not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = GroupSerializer(group, data=request.data, partial=True)
    if serializer.is_valid():
        group = serializer.save()
        return Response(GroupSerializer(group).data, status=status.HTTP_200_OK)

    return Response({'detail': format_serializer_errors(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """
    Change password for authenticated user.
    POST /api/auth/change-password
    """
    serializer = ChangePasswordSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        revoke_all_user_sessions(user)
        
        return Response({
            'message': 'Password changed successfully. Please log in again.'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/h', method='POST')
def google_oauth_callback_view(request):
    """
    Google OAuth callback endpoint.
    POST /api/auth/google/callback
    """
    google_client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    if not google_client_id or google_client_id.startswith('your-'):
        return Response({
            'error': 'Google login is not configured on the server'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    serializer = GoogleOAuthSerializer(data=request.data)
    
    if serializer.is_valid():
        id_token_str = serializer.validated_data['id_token']
        
        try:
            # Verify Google ID token
            idinfo = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=30
            )
            
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Invalid issuer')
            
            email = idinfo['email']
            if not idinfo.get('email_verified', False):
                raise ValueError('Google email is not verified')

            google_id = idinfo['sub']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            picture_url = idinfo.get('picture', '')
            
            # Link an existing email account first, otherwise create a new Google user.
            user = User.objects.filter(google_id=google_id).first()

            if not user:
                user = User.objects.filter(email=email).first()

                if user:
                    update_fields = []
                    if user.google_id != google_id:
                        user.google_id = google_id
                        update_fields.append('google_id')
                    if not user.is_email_verified:
                        user.is_email_verified = True
                        update_fields.append('is_email_verified')
                    if first_name and not user.first_name:
                        user.first_name = first_name
                        update_fields.append('first_name')
                    if last_name and not user.last_name:
                        user.last_name = last_name
                        update_fields.append('last_name')
                    should_set_google_avatar = bool(picture_url and not user.avatar_url)
                    if should_set_google_avatar:
                        user.avatar_url = picture_url
                        update_fields.append('avatar_url')
                    if update_fields:
                        user.save(update_fields=update_fields)
                else:
                    user = User.objects.create(
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        username=email,
                        google_id=google_id,
                        is_email_verified=True,
                        avatar_url=picture_url,
                    )
                    user.set_unusable_password()
                    user.save(update_fields=['password'])
            else:
                updated_fields = []
                if first_name and not user.first_name:
                    user.first_name = first_name
                    updated_fields.append('first_name')
                if last_name and not user.last_name:
                    user.last_name = last_name
                    updated_fields.append('last_name')
                if picture_url and not user.avatar_url:
                    user.avatar_url = picture_url
                    updated_fields.append('avatar_url')

                if updated_fields:
                    user.save(update_fields=updated_fields)

            if not user.is_active:
                return Response({
                    'detail': 'This account is locked. Please contact an administrator.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if user.is_two_factor_enabled:
                try:
                    challenge = send_login_2fa_challenge(user)
                except EmailDeliveryError:
                    return Response({
                        'detail': 'Unable to send login verification code right now. Please try again later.'
                    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

                return Response({
                    'message': 'Two-factor verification required. We sent an OTP to your email.',
                    'requires_2fa': True,
                    'email': user.email,
                    'challenge_token': challenge.token,
                    'expires_at': challenge.expires_at,
                }, status=status.HTTP_200_OK)

            return Response(
                issue_auth_response(user, request, 'Google login successful'),
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error("Google OAuth error: %s", str(e), exc_info=True)
            response_data = {'error': 'Invalid Google token'}
            if settings.DEBUG:
                response_data['detail'] = str(e)
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_view(request):
    """
    Get current authenticated user info.
    GET /api/auth/me
    """
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile_view(request):
    """
    Update user profile.
    PUT /api/auth/profile
    """
    serializer = UserSerializer(
        request.user,
        data=request.data,
        partial=True
    )
    
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_two_factor_view(request):
    """
    Enable or disable email OTP two-factor authentication for the current user.
    POST /api/auth/2fa
    Body: {"enabled": true}
    """
    serializer = TwoFactorToggleSerializer(data=request.data)

    if serializer.is_valid():
        user = request.user
        enabled = serializer.validated_data['enabled']

        if enabled and not user.is_email_verified:
            return Response({
                'detail': 'Please verify your email before enabling two-factor authentication.'
            }, status=status.HTTP_400_BAD_REQUEST)

        user.is_two_factor_enabled = enabled
        user.save(update_fields=['is_two_factor_enabled'])

        if not enabled:
            TwoFactorLoginChallenge.objects.filter(
                user=user,
                is_used=False
            ).update(is_used=True, verified_at=timezone.now())

        return Response({
            'message': 'Two-factor authentication enabled.' if enabled else 'Two-factor authentication disabled.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)

    return Response({
        'detail': format_serializer_errors(serializer.errors)
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_avatar_view(request):
    """
    Upload avatar via backend (server-side Cloudinary upload).
    POST /api/auth/profile/avatar
    Form-data: avatar=<file>
    """
    if not (settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET):
        return Response({'error': 'Cloudinary not configured on server.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    avatar_file = request.FILES.get('avatar')
    if not avatar_file:
        return Response({'error': 'Avatar file is required.'}, status=status.HTTP_400_BAD_REQUEST)

    max_size = getattr(settings, 'MAX_AVATAR_UPLOAD_SIZE', 100 * 1024 * 1024)
    if avatar_file.size > max_size:
        return Response({'error': 'Avatar file too large. Max 100MB.'}, status=status.HTTP_400_BAD_REQUEST)

    allowed_types = {'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'}
    content_type = getattr(avatar_file, 'content_type', '')
    if content_type not in allowed_types:
        return Response({'error': 'Unsupported image format. Use JPG, PNG, WEBP, or GIF.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        result = uploader.upload(
            avatar_file,
            folder='avatars',
            resource_type='image',
            overwrite=True,
            invalidate=True,
        )
    except CloudinaryError as exc:
        logger.error("Cloudinary upload failed: %s", exc)
        return Response({'error': 'Cloudinary upload failed.'}, status=status.HTTP_502_BAD_GATEWAY)

    secure_url = result.get('secure_url')
    if not secure_url:
        return Response({'error': 'Upload did not return a secure URL.'}, status=status.HTTP_502_BAD_GATEWAY)

    request.user.avatar_url = secure_url
    request.user.save(update_fields=['avatar_url'])
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cloudinary_signature_view(request):
    """
    Create a Cloudinary signature for signed uploads.
    POST /api/auth/cloudinary/sign
    Request body may include optional `public_id` or `folder` to include in the signature.
    Response: { api_key, timestamp, signature, cloud_name }
    """
    import time
    import hashlib

    if not getattr(settings, 'CLOUDINARY_API_SECRET', ''):
        return Response({'error': 'Cloudinary not configured on server.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    timestamp = int(time.time())

    # Allowed params to include in signature
    params = {'timestamp': timestamp}
    for key in ('public_id', 'folder'):
        val = request.data.get(key)
        if val:
            params[key] = val

    # Build string to sign by sorting keys
    sign_parts = [f"{k}={params[k]}" for k in sorted(params.keys())]
    to_sign = '&'.join(sign_parts)
    signature = hashlib.sha1((to_sign + settings.CLOUDINARY_API_SECRET).encode('utf-8')).hexdigest()

    return Response({
        'api_key': settings.CLOUDINARY_API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'cloud_name': settings.CLOUDINARY_CLOUD_NAME,
    }, status=status.HTTP_200_OK)
