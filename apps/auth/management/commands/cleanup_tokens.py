from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.auth.models import (
    EmailVerificationToken, OTPToken, PasswordResetToken, AuthSession
)


class Command(BaseCommand):
    help = 'Clean up expired authentication tokens and sessions'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Delete inactive sessions older than this many days'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Cleaning up expired tokens...')
        
        now = timezone.now()
        
        # Delete expired email verification tokens
        expired_email_tokens = EmailVerificationToken.objects.filter(
            expires_at__lt=now,
            is_used=False
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {expired_email_tokens[0]} expired email verification tokens'
            )
        )
        
        # Delete expired OTP tokens
        expired_otp_tokens = OTPToken.objects.filter(
            expires_at__lt=now,
            is_used=False
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {expired_otp_tokens[0]} expired OTP tokens'
            )
        )
        
        # Delete expired password reset tokens
        expired_reset_tokens = PasswordResetToken.objects.filter(
            expires_at__lt=now,
            is_used=False
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {expired_reset_tokens[0]} expired password reset tokens'
            )
        )
        
        # Clean up old inactive sessions
        cutoff_date = now - timedelta(days=options['days'])
        old_sessions = AuthSession.objects.filter(
            created_at__lt=cutoff_date,
            is_active=False
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {old_sessions[0]} old inactive sessions'
            )
        )
        
        self.stdout.write(
            self.style.SUCCESS('Token cleanup completed successfully!')
        )
