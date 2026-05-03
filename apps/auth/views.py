import logging
import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, action, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from cloudinary import uploader
from cloudinary.exceptions import Error as CloudinaryError

from .models import User, EmailVerificationToken, OTPToken, PasswordResetToken, AuthSession
from .serializers import (
    UserSerializer, SignUpSerializer, LoginSerializer, OTPRequestSerializer,
    OTPVerifySerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    EmailVerificationSerializer, ChangePasswordSerializer, AuthSessionSerializer,
    GoogleOAuthSerializer
)

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when transactional email cannot be delivered."""


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
            # Send verification email
            verification_token = EmailVerificationToken.objects.get(user=user)
            email_context = {
                'user_name': user.get_full_name() or user.email,
                'verification_link': f"{settings.GOOGLE_OAUTH_REDIRECT_URI.split('/api')[0]}/verify-email?token={verification_token.token}"
            }
            
            send_email(
                subject='Verify Your Email',
                email_to=user.email,
                template_name='verify_email',
                context=email_context
            )

            # Send signup OTP
            otp_token = OTPToken.create_otp(user, purpose='signup')
            otp_context = {
                'user_name': user.get_full_name() or user.email,
                'otp': otp_token.otp,
                'expiry_minutes': settings.OTP_EXPIRY_MINUTES
            }
            send_email(
                subject='Verify Your Email - OTP',
                email_to=user.email,
                template_name='signup_otp',
                context=otp_context
            )
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
        user.update_last_login()
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Create session
        session = create_auth_session(user, request, refresh)
        
        return Response({
            'message': 'Login successful',
            'user': UserSerializer(user).data,
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            'session_id': str(session.id)
        }, status=status.HTTP_200_OK)
    
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
        
        # For login 2FA, generate JWT tokens
        user.update_last_login()
        refresh = RefreshToken.for_user(user)
        session = create_auth_session(user, request, refresh)
        
        return Response({
            'message': 'OTP verified. Login successful.',
            'user': UserSerializer(user).data,
            'tokens': {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            'session_id': str(session.id)
        }, status=status.HTTP_200_OK)
    
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
        
        # Revoke all sessions
        AuthSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            revoked_at=timezone.now()
        )
        
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
        
        # Revoke all sessions except current
        AuthSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            revoked_at=timezone.now()
        )
        
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
    serializer = GoogleOAuthSerializer(data=request.data)
    
    if serializer.is_valid():
        id_token_str = serializer.validated_data['id_token']
        
        try:
            # Verify Google ID token
            idinfo = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
            
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Invalid issuer')
            
            email = idinfo['email']
            google_id = idinfo['sub']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            picture_url = idinfo.get('picture', '')
            
            # Link an existing email account first, otherwise create a new Google user.
            user = User.objects.filter(google_id=google_id).first()

            if not user:
                user = User.objects.filter(email=email).first()

                if user:
                    user.google_id = google_id
                    user.is_email_verified = True
                    if first_name and not user.first_name:
                        user.first_name = first_name
                    if last_name and not user.last_name:
                        user.last_name = last_name
                    if picture_url and not user.avatar_url:
                        user.avatar_url = picture_url
                    user.save(update_fields=['google_id', 'is_email_verified', 'first_name', 'last_name', 'avatar_url'])
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
            else:
                updated_fields = []
                if user.email != email:
                    user.email = email
                    updated_fields.append('email')
                if first_name and user.first_name != first_name:
                    user.first_name = first_name
                    updated_fields.append('first_name')
                if last_name and user.last_name != last_name:
                    user.last_name = last_name
                    updated_fields.append('last_name')
                if picture_url and user.avatar_url != picture_url:
                    user.avatar_url = picture_url
                    updated_fields.append('avatar_url')

                if updated_fields:
                    user.save(update_fields=updated_fields)
            
            # Update last login
            user.update_last_login()
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            # Create session
            session = create_auth_session(user, request, refresh)
            
            return Response({
                'message': 'Google login successful',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
                'session_id': str(session.id)
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Google OAuth error: {str(e)}")
            return Response({
                'error': 'Invalid Google token'
            }, status=status.HTTP_400_BAD_REQUEST)
    
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
