from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.documents.models import Document
from apps.documents.serializers import DocumentSerializer, DocumentUploadSerializer
from apps.chatbot.models import ChatSession
from .models import (
    ChatDocumentAttachment,
    DocumentShare,
    InAppNotification,
    Team,
    TeamDocument,
    TeamInvitation,
    TeamMembership,
)
from .permissions import user_can_access_document, user_is_team_member
from apps.realtime.events import send_notification


User = get_user_model()


class TeamMemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = TeamMembership
        fields = ['id', 'user', 'email', 'full_name', 'role', 'joined_at']
        read_only_fields = fields


class TeamSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'owner', 'members', 'member_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'owner', 'members', 'member_count', 'created_at', 'updated_at']

    def get_members(self, obj):
        return TeamMemberSerializer(obj.memberships.select_related('user'), many=True).data

    def get_member_count(self, obj):
        return obj.memberships.count()


class TeamInvitationSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)
    invited_by_email = serializers.EmailField(source='invited_by.email', read_only=True)

    class Meta:
        model = TeamInvitation
        fields = [
            'id', 'team', 'team_name', 'email', 'status', 'invited_by',
            'invited_by_email', 'created_at', 'expires_at', 'responded_at'
        ]
        read_only_fields = fields


class TeamInviteSerializer(serializers.Serializer):
    emails = serializers.ListField(child=serializers.EmailField(), allow_empty=False)

    def validate_emails(self, value):
        normalized = []
        seen = set()
        for email in value:
            clean = email.strip().lower()
            if clean and clean not in seen:
                normalized.append(clean)
                seen.add(clean)
        return normalized

    def create(self, validated_data):
        request = self.context['request']
        team = self.context['team']
        created = []
        skipped = []

        with transaction.atomic():
            for email in validated_data['emails']:
                invited_user = User.objects.filter(email__iexact=email).first()
                if invited_user and TeamMembership.objects.filter(team=team, user=invited_user).exists():
                    skipped.append({'email': email, 'reason': 'already_member'})
                    continue
                if TeamInvitation.objects.filter(team=team, email__iexact=email, status=TeamInvitation.Status.PENDING).exists():
                    skipped.append({'email': email, 'reason': 'pending_invitation_exists'})
                    continue

                invitation = TeamInvitation.objects.create(
                    team=team,
                    invited_by=request.user,
                    invited_user=invited_user,
                    email=email,
                )
                created.append(invitation)

                if invited_user:
                    notification = InAppNotification.objects.create(
                        user=invited_user,
                        title='Team invitation',
                        message=f'{request.user.email} invited you to join {team.name}.',
                        data={'type': 'team_invitation', 'invitation_id': str(invitation.id), 'team_id': team.id},
                    )
                    send_notification(notification)

                send_mail(
                    subject=f'Invitation to join {team.name}',
                    message=f'{request.user.email} invited you to join team "{team.name}". Please open the app to accept or reject the invitation.',
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=True,
                )

        return {'created': created, 'skipped': skipped}


class TeamDocumentSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)
    uploaded_by_email = serializers.EmailField(source='uploaded_by.email', read_only=True)
    file_name = serializers.CharField(source='document.title', read_only=True)
    file_type = serializers.CharField(source='document.file_type', read_only=True)
    file_size = serializers.SerializerMethodField()

    class Meta:
        model = TeamDocument
        fields = [
            'id', 'team', 'document', 'file_name', 'file_type', 'file_size',
            'uploaded_by', 'uploaded_by_email', 'created_at'
        ]
        read_only_fields = fields

    def get_file_size(self, obj):
        try:
            return obj.document.file.size if obj.document.file else 0
        except Exception:
            return 0


class ChatAttachDocumentsSerializer(serializers.Serializer):
    chat_session_id = serializers.IntegerField()
    document_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate(self, attrs):
        request = self.context['request']
        chat_session = ChatSession.objects.filter(id=attrs['chat_session_id'], user=request.user, is_deleted=False).first()
        if not chat_session:
            raise serializers.ValidationError({'chat_session_id': 'Chat session is not available.'})

        documents = list(Document.objects.filter(id__in=attrs['document_ids'], is_deleted=False))
        found_ids = {doc.id for doc in documents}
        missing = [doc_id for doc_id in attrs['document_ids'] if doc_id not in found_ids]
        if missing:
            raise serializers.ValidationError({'document_ids': f'Documents not found: {missing}'})

        denied = [doc.id for doc in documents if not user_can_access_document(request.user, doc)]
        if denied:
            raise serializers.ValidationError({'document_ids': f'No permission for documents: {denied}'})

        attrs['chat_session'] = chat_session
        attrs['documents'] = documents
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        created = []
        skipped = []
        for doc in validated_data['documents']:
            attachment, was_created = ChatDocumentAttachment.objects.get_or_create(
                chat_session=validated_data['chat_session'],
                document=doc,
                defaults={'attached_by': request.user},
            )
            if was_created:
                created.append(attachment)
            else:
                skipped.append(doc.id)
        return {'created': created, 'skipped': skipped}


class DocumentShareSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.title', read_only=True)
    shared_by_email = serializers.EmailField(source='shared_by.email', read_only=True)
    shared_with_email = serializers.EmailField(source='shared_with.email', read_only=True)

    class Meta:
        model = DocumentShare
        fields = [
            'id', 'document', 'document_title', 'shared_by', 'shared_by_email',
            'shared_with', 'shared_with_email', 'can_download', 'created_at'
        ]
        read_only_fields = fields


class CreateDocumentShareSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise serializers.ValidationError('No user exists with this Gmail address.')
        self.context['shared_with'] = user
        return email

    def validate(self, attrs):
        request = self.context['request']
        document = self.context['document']
        if not user_can_access_document(request.user, document):
            raise serializers.ValidationError('You do not have permission to share this document.')
        if document.uploaded_by_id != request.user.id and document.chat_session.user_id != request.user.id and not request.user.is_staff:
            raise serializers.ValidationError('Only the document owner can share this document.')
        if document.team_links.exists():
            raise serializers.ValidationError('Team documents cannot be shared with individual users.')
        if self.context['shared_with'] == request.user:
            raise serializers.ValidationError('You cannot share a document with yourself.')
        if DocumentShare.objects.filter(document=document, shared_with=self.context['shared_with']).exists():
            raise serializers.ValidationError('This document is already shared with that user.')
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        document = self.context['document']
        shared_with = self.context['shared_with']
        share = DocumentShare.objects.create(
            document=document,
            shared_by=request.user,
            shared_with=shared_with,
            can_download=True,
        )
        notification = InAppNotification.objects.create(
            user=shared_with,
            title='Document shared with you',
            message=f'{request.user.email} shared "{document.title}" with you.',
            data={'type': 'document_share', 'document_id': document.id, 'share_id': share.id},
        )
        send_notification(notification)
        send_mail(
            subject=f'Document shared: {document.title}',
            message=f'{request.user.email} shared "{document.title}" with you. Open the Library to view or download it.',
            from_email=None,
            recipient_list=[shared_with.email],
            fail_silently=True,
        )
        return share
