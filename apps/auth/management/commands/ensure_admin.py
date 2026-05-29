from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.auth.models import User


class Command(BaseCommand):
    help = 'Create or update a staff/superuser admin account.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Admin email.')
        parser.add_argument('--password', required=True, help='Admin password.')
        parser.add_argument('--first-name', default='Admin')
        parser.add_argument('--last-name', default='User')

    @transaction.atomic
    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        password = options['password']

        if not email:
            raise CommandError('Admin email is required.')
        if len(password) < 8:
            raise CommandError('Admin password must be at least 8 characters.')

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': options['first_name'],
                'last_name': options['last_name'],
                'is_email_verified': True,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        user.username = user.username or email
        user.email = email
        user.first_name = user.first_name or options['first_name']
        user.last_name = user.last_name or options['last_name']
        user.is_email_verified = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} admin account: {email}'))
