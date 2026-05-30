import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('apps_auth', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_two_factor_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='TwoFactorLoginChallenge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('token', models.CharField(db_index=True, max_length=255, unique=True)),
                ('is_used', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('otp_token', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='login_challenge', to='apps_auth.otptoken')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='two_factor_login_challenges', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Two-Factor Login Challenge',
                'verbose_name_plural': 'Two-Factor Login Challenges',
                'indexes': [
                    models.Index(fields=['user', 'is_used'], name='apps_auth_t_user_id_64d2af_idx'),
                    models.Index(fields=['expires_at'], name='apps_auth_t_expires_3db050_idx'),
                ],
            },
        ),
    ]
