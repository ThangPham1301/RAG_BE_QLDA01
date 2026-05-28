from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document
from apps.documents.serializers import DocumentSerializer, DocumentUploadSerializer
from .models import ChatDocumentAttachment, DocumentShare, InAppNotification, Team, TeamDocument, TeamInvitation, TeamMembership
from .permissions import accessible_documents_for_user, user_can_access_document, user_is_team_member
from .serializers import (
    ChatAttachDocumentsSerializer,
    CreateDocumentShareSerializer,
    DocumentShareSerializer,
    TeamDocumentSerializer,
    TeamInvitationSerializer,
    TeamInviteSerializer,
    TeamSerializer,
)


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return Team.objects.filter(memberships__user=self.request.user).distinct().order_by('-created_at')

    def perform_create(self, serializer):
        team = serializer.save(owner=self.request.user)
        TeamMembership.objects.create(team=team, user=self.request.user, role=TeamMembership.Role.OWNER)

    def _require_owner(self, team):
        return TeamMembership.objects.filter(team=team, user=self.request.user, role=TeamMembership.Role.OWNER).exists()

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        team = self.get_object()
        if not self._require_owner(team):
            return Response({'error': 'Only team owners can invite users.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = TeamInviteSerializer(data=request.data, context={'request': request, 'team': team})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response({
            'created': TeamInvitationSerializer(result['created'], many=True).data,
            'skipped': result['skipped'],
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get', 'post'], url_path='documents')
    def documents(self, request, pk=None):
        team = self.get_object()
        if request.method.lower() == 'get':
            links = TeamDocument.objects.filter(team=team, document__is_deleted=False).select_related(
                'document', 'document__chat_session', 'document__chat_session__project', 'uploaded_by'
            )
            return Response(TeamDocumentSerializer(links, many=True, context={'request': request}).data)

        chat_session_id = request.data.get('chat_session_id')
        if not chat_session_id:
            from apps.chatbot.models import ChatSession
            from apps.projects.models import Project
            project = Project.objects.filter(owner=request.user, name=f'Team Workspace - {team.name}').first()
            if not project:
                project = Project.objects.create(
                    owner=request.user,
                    name=f'Team Workspace - {team.name}',
                    description=f'Workspace for shared team documents in {team.name}.',
                )
            chat_session = ChatSession.objects.filter(
                project=project,
                user=request.user,
                title=f'Team Documents - {team.name}',
            ).first()
            if not chat_session:
                chat_session = ChatSession.objects.create(
                    project=project,
                    user=request.user,
                    title=f'Team Documents - {team.name}',
                    description=f'Shared documents uploaded for {team.name}.',
                )
            chat_session_id = chat_session.id

        files = request.FILES.getlist('files') or [request.FILES.get('file')]
        files = [file_obj for file_obj in files if file_obj]
        if not files:
            return Response({'error': 'No files provided.'}, status=status.HTTP_400_BAD_REQUEST)

        created_docs = []
        errors = []
        from apps.documents.views import DocumentViewSet
        indexer = DocumentViewSet()

        for file_obj in files:
            data = {'chat_session_id': chat_session_id, 'title': request.data.get('title', ''), 'file': file_obj}
            upload_serializer = DocumentUploadSerializer(data=data, context={'request': request})
            if not upload_serializer.is_valid():
                errors.append({file_obj.name: upload_serializer.errors})
                continue
            doc = upload_serializer.save()
            TeamDocument.objects.get_or_create(team=team, document=doc, defaults={'uploaded_by': request.user})
            indexer._schedule_indexing(doc)
            doc.refresh_from_db()
            created_docs.append(doc)

        if not created_docs and errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'documents': DocumentSerializer(created_docs, many=True, context={'request': request}).data,
            'errors': errors,
        }, status=status.HTTP_201_CREATED)


class TeamInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        invitations = TeamInvitation.objects.filter(
            Q(invited_user=self.request.user) | Q(email__iexact=self.request.user.email)
        ).select_related('team', 'invited_by')
        for invitation in invitations.filter(status=TeamInvitation.Status.PENDING):
            invitation.mark_expired_if_needed()
        return invitations.order_by('-created_at')

    def _respond(self, request, pk, target_status):
        invitation = self.get_object()
        invitation.mark_expired_if_needed()
        if invitation.status != TeamInvitation.Status.PENDING:
            return Response({'error': f'Invitation already responded with status {invitation.status}.'}, status=status.HTTP_409_CONFLICT)

        if target_status == TeamInvitation.Status.ACCEPTED:
            TeamMembership.objects.get_or_create(team=invitation.team, user=request.user, defaults={'role': TeamMembership.Role.MEMBER})

        invitation.status = target_status
        invitation.invited_user = request.user
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=['status', 'invited_user', 'responded_at'])
        return Response(TeamInvitationSerializer(invitation).data)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        return self._respond(request, pk, TeamInvitation.Status.ACCEPTED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._respond(request, pk, TeamInvitation.Status.REJECTED)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InAppNotification.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        data = [
            {
                'id': item.id,
                'title': item.title,
                'message': item.message,
                'data': item.data,
                'is_read': item.is_read,
                'created_at': item.created_at.isoformat(),
            }
            for item in self.get_queryset()
        ]
        return Response(data)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'status': 'ok'})


class ChatDocumentAttachmentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChatAttachDocumentsSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response({
            'attached': [item.document_id for item in result['created']],
            'skipped': result['skipped'],
        }, status=status.HTTP_201_CREATED)

    def delete(self, request):
        chat_session_id = request.data.get('chat_session_id') or request.query_params.get('chat_session_id')
        document_id = request.data.get('document_id') or request.query_params.get('document_id')
        if not chat_session_id or not document_id:
            return Response({'error': 'chat_session_id and document_id are required.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.chatbot.models import ChatSession

        session = ChatSession.objects.filter(id=chat_session_id, user=request.user, is_deleted=False).first()
        if not session:
            return Response({'error': 'Chat session is not available.'}, status=status.HTTP_404_NOT_FOUND)

        deleted, _ = ChatDocumentAttachment.objects.filter(
            chat_session=session,
            document_id=document_id,
        ).delete()
        if not deleted:
            return Response({'error': 'Document is not attached to this chat.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SharedLibraryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        base = accessible_documents_for_user(request.user).select_related('chat_session', 'chat_session__project', 'uploaded_by')
        my_documents = base.filter(chat_session__user=request.user, team_links__isnull=True).exclude(user_shares__shared_with=request.user).distinct()
        shared_with_me = base.filter(user_shares__shared_with=request.user).exclude(uploaded_by=request.user).distinct()
        team_documents = base.filter(team_links__team__memberships__user=request.user).distinct()

        return Response({
            'my_documents': DocumentSerializer(my_documents, many=True, context={'request': request}).data,
            'shared_with_me': DocumentSerializer(shared_with_me, many=True, context={'request': request}).data,
            'team_documents': DocumentSerializer(team_documents, many=True, context={'request': request}).data,
        })
