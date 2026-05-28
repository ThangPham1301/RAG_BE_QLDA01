import datetime
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '0005_rename_documents_d_chat_se_idx_documents_d_chat_se_017659_idx'),
        ('chatbot', '0003_remove_selected_document_ids'),
    ]

    operations = [
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='owned_teams', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['owner', '-created_at'], name='teams_team_owner_i_d9a21d_idx'), models.Index(fields=['name'], name='teams_team_name_f58822_idx')],
            },
        ),
        migrations.CreateModel(
            name='TeamMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('owner', 'Owner'), ('member', 'Member')], default='member', max_length=20)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='teams.team')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['team_id', 'user__email'],
                'indexes': [models.Index(fields=['team', 'role'], name='teams_teamm_team_id_58bb87_idx'), models.Index(fields=['user'], name='teams_teamm_user_id_e86f41_idx')],
                'unique_together': {('team', 'user')},
            },
        ),
        migrations.CreateModel(
            name='TeamInvitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(db_index=True, max_length=254)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('ACCEPTED', 'Accepted'), ('REJECTED', 'Rejected'), ('EXPIRED', 'Expired')], default='PENDING', max_length=20)),
                ('token', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('invited_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_team_invitations', to=settings.AUTH_USER_MODEL)),
                ('invited_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='team_invitations', to=settings.AUTH_USER_MODEL)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='teams.team')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['email', 'status'], name='teams_teami_email_021155_idx'), models.Index(fields=['team', 'status'], name='teams_teami_team_id_f5f09d_idx')],
            },
        ),
        migrations.CreateModel(
            name='InAppNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160)),
                ('message', models.TextField()),
                ('data', models.JSONField(blank=True, default=dict)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', 'is_read', '-created_at'], name='teams_inapp_user_id_a8ee8f_idx')],
            },
        ),
        migrations.CreateModel(
            name='TeamDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_links', to='documents.document')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_documents', to='teams.team')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='team_document_uploads', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['team', '-created_at'], name='teams_teamd_team_id_e7ab7e_idx'), models.Index(fields=['document'], name='teams_teamd_documen_af0d55_idx')],
                'unique_together': {('team', 'document')},
            },
        ),
        migrations.CreateModel(
            name='DocumentShare',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('can_download', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_shares', to='documents.document')),
                ('shared_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_document_shares', to=settings.AUTH_USER_MODEL)),
                ('shared_with', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_document_shares', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['shared_with', '-created_at'], name='teams_docum_shared_2a9c9b_idx'), models.Index(fields=['document'], name='teams_docum_documen_fdb779_idx')],
                'unique_together': {('document', 'shared_with')},
            },
        ),
        migrations.CreateModel(
            name='ChatDocumentAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('attached_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_document_attachments', to=settings.AUTH_USER_MODEL)),
                ('chat_session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shared_document_attachments', to='chatbot.chatsession')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_attachments', to='documents.document')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['chat_session', '-created_at'], name='teams_chatd_chat_se_f03e94_idx'), models.Index(fields=['document'], name='teams_chatd_documen_c99af4_idx')],
                'unique_together': {('chat_session', 'document')},
            },
        ),
    ]
