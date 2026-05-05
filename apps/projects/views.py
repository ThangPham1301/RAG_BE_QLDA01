from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
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
        docs = Document.objects.filter(project=project, is_deleted=False)
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
