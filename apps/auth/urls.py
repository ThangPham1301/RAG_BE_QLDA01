from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

app_name = 'auth'

urlpatterns = [
    # Authentication endpoints
    path('signup', views.signup_view, name='signup'),
    path('verify-email', views.verify_email_view, name='verify_email'),
    path('login', views.login_view, name='login'),
    path('logout', views.logout_view, name='logout'),
    path('logout-device', views.logout_device_view, name='logout_device'),
    
    # OTP endpoints
    path('request-otp', views.request_otp_view, name='request_otp'),
    path('verify-otp', views.verify_otp_view, name='verify_otp'),
    
    # Password reset endpoints
    path('password-reset/request', views.password_reset_request_view, name='password_reset_request'),
    path('password-reset/confirm', views.password_reset_confirm_view, name='password_reset_confirm'),
    
    # OAuth endpoints
    path('google/callback', views.google_oauth_callback_view, name='google_callback'),
    
    # User endpoints
    path('me', views.current_user_view, name='current_user'),
    path('profile', views.update_profile_view, name='update_profile'),
    path('profile/avatar', views.upload_avatar_view, name='upload_avatar'),
    path('cloudinary/sign', views.cloudinary_signature_view, name='cloudinary_sign'),
    path('change-password', views.change_password_view, name='change_password'),
    path('sessions', views.get_sessions_view, name='get_sessions'),
    
    # Token endpoints
    path('token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
]
