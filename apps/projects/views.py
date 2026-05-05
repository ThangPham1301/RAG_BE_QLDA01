from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.db.models import Count, Q, Sum
from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def documents(self, request, pk=None):
        """Get all documents in this project"""
        project = self.get_object()
        from apps.documents.models import Document
        docs = Document.objects.filter(chat_session__project=project, is_deleted=False).select_related('chat_session', 'chat_session__project')
        from apps.documents.serializers import DocumentSerializer
        serializer = DocumentSerializer(docs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def chats(self, request, pk=None):
        """Get all chat sessions in this project"""
        project = self.get_object()
        from apps.chatbot.models import ChatSession
        chats = ChatSession.objects.filter(project=project, user=request.user, is_deleted=False).order_by('-updated_at')
        from apps.chatbot.serializers import ChatSessionSerializer
        serializer = ChatSessionSerializer(chats, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """User-wide dashboard metrics and recent activity."""
        projects_qs = self.get_queryset()
        from apps.documents.models import Document
        from apps.chatbot.models import ChatSession

        documents_qs = Document.objects.filter(
<<<<<<< HEAD
            project__in=projects_qs,
            is_deleted=False,
        ).select_related('project', 'uploaded_chat_session')
=======
            chat_session__project__in=projects_qs,
            is_deleted=False,
        ).select_related('chat_session', 'chat_session__project')
>>>>>>> 5f5f0ac (fix chat structure)

        counts = documents_qs.aggregate(
            total_documents=Count('id'),
            indexed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXED)),
            indexing_documents=Count('id', filter=Q(index_status=Document.IndexStatus.INDEXING)),
            failed_documents=Count('id', filter=Q(index_status=Document.IndexStatus.FAILED)),
            total_indexed_chunks=Sum('indexed_chunks'),
        )

        active_chat_sessions = ChatSession.objects.filter(
            project__in=projects_qs,
            user=request.user,
            is_deleted=False,
            is_archived=False,
        ).count()

        recent_uploads = []
        for doc in documents_qs.order_by('-uploaded_at')[:8]:
            recent_uploads.append({
                'document_id': doc.id,
                'title': doc.title,
<<<<<<< HEAD
                'project_id': doc.project_id,
                'project_name': doc.project.name,
                'chat_session_id': doc.uploaded_chat_session_id,
                'chat_session_title': doc.uploaded_chat_session.title if doc.uploaded_chat_session else None,
=======
                'project_id': doc.chat_session.project_id,
                'project_name': doc.chat_session.project.name,
                'chat_session_id': doc.chat_session_id,
                'chat_session_title': doc.chat_session.title,
>>>>>>> 5f5f0ac (fix chat structure)
                'index_status': doc.index_status,
                'uploaded_at': doc.uploaded_at.isoformat(),
            })

        return Response({
            'total_projects': projects_qs.count(),
            'total_documents': counts['total_documents'] or 0,
            'indexed_documents': counts['indexed_documents'] or 0,
            'indexing_documents': counts['indexing_documents'] or 0,
            'failed_documents': counts['failed_documents'] or 0,
            'total_indexed_chunks': counts['total_indexed_chunks'] or 0,
            'active_chat_sessions': active_chat_sessions,
            'recent_uploads': recent_uploads,
        })
