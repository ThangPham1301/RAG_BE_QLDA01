import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Team(models.Model):
    name = models.CharField(max_length=160)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_teams')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        MEMBER = 'member', 'Member'

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_memberships')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('team', 'user')]
        ordering = ['team_id', 'user__email']
        indexes = [
            models.Index(fields=['team', 'role']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f'{self.user.email} in {self.team.name}'


class TeamInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'
        EXPIRED = 'EXPIRED', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_team_invitations')
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_invitations', null=True, blank=True)
    email = models.EmailField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'status']),
            models.Index(fields=['team', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=14)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and self.expires_at and timezone.now() >= self.expires_at

    def mark_expired_if_needed(self):
        if self.is_expired:
            self.status = self.Status.EXPIRED
            self.responded_at = timezone.now()
            self.save(update_fields=['status', 'responded_at'])
            return True
        return False

    def __str__(self):
        return f'{self.email} -> {self.team.name} ({self.status})'


class InAppNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=160)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]


class TeamDocument(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team_documents')
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='team_links')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_document_uploads')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('team', 'document')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['team', '-created_at']),
            models.Index(fields=['document']),
        ]


class DocumentShare(models.Model):
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='user_shares')
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_document_shares')
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_document_shares')
    can_download = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('document', 'shared_with')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['shared_with', '-created_at']),
            models.Index(fields=['document']),
        ]


class ChatDocumentAttachment(models.Model):
    chat_session = models.ForeignKey('chatbot.ChatSession', on_delete=models.CASCADE, related_name='shared_document_attachments')
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='chat_attachments')
    attached_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_document_attachments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('chat_session', 'document')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['chat_session', '-created_at']),
            models.Index(fields=['document']),
        ]
