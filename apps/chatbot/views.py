import logging
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from .models import ChatSession, ChatMessage, ChatFeedback
from .serializers import (
    ChatSessionSerializer, ChatSessionDetailSerializer,
    ChatMessageSerializer, ChatMessageCreateSerializer, ChatFeedbackSerializer
)

logger = logging.getLogger(__name__)


class ChatSessionViewSet(viewsets.ModelViewSet):
    """Chat session management"""
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ChatSession.objects.filter(
            user=self.request.user,
            is_deleted=False
        ).order_by('-updated_at')

        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ChatSessionDetailSerializer
        return ChatSessionSerializer

    def create(self, request, *args, **kwargs):
        """Create new chat session"""
        data = request.data.copy()
        project_id = data.get('project_id')
        if not project_id:
            return Response({'error': 'project_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        from apps.projects.models import Project
        if not Project.objects.filter(id=project_id, owner=request.user).exists():
            return Response({'error': 'project is not available'}, status=status.HTTP_400_BAD_REQUEST)
        data['project'] = project_id
        data['user'] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Delete session and cascade its documents"""
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Send message to chat session and get RAG response"""
        session = self.get_object()
        
        serializer = ChatMessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        content = serializer.validated_data['content']

        try:
            # Import here to avoid circular imports
            from .chat_service import ChatService

            chat_service = ChatService()

            # document_id optional — cho phép hỏi về 1 file cụ thể
            document_id = request.data.get('document_id')
            document_id = int(document_id) if document_id else None
            if document_id:
                from apps.documents.models import Document
                from apps.teams.permissions import user_can_access_document
                document = Document.objects.filter(id=document_id, is_deleted=False).first()
                if not document or not user_can_access_document(request.user, document):
                    return Response({'error': 'document is not available'}, status=status.HTTP_403_FORBIDDEN)

            # Get RAG response
            response_data = chat_service.ask_question(session.id, content, document_id=document_id)

            # Update session timestamp
            session.last_message_at = timezone.now()
            session.save(update_fields=['last_message_at'])

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in send_message: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get all messages in session"""
        session = self.get_object()
        messages = session.messages.order_by('created_at')
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)


class ChatSendView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('chat_session_id')
        if not session_id:
            return Response({'error': 'chat_session_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        session = get_object_or_404(ChatSession, id=session_id, user=request.user, is_deleted=False)
        serializer = ChatMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            from .chat_service import ChatService

            chat_service = ChatService()

            # document_id optional — cho phép hỏi về 1 file cụ thể
            document_id = request.data.get('document_id')
            document_id = int(document_id) if document_id else None
            if document_id:
                from apps.documents.models import Document
                from apps.teams.permissions import user_can_access_document
                document = Document.objects.filter(id=document_id, is_deleted=False).first()
                if not document or not user_can_access_document(request.user, document):
                    return Response({'error': 'document is not available'}, status=status.HTTP_403_FORBIDDEN)

            response_data = chat_service.ask_question(
                session.id,
                serializer.validated_data['content'],
                document_id=document_id,
            )
            session.last_message_at = timezone.now()
            session.save(update_fields=['last_message_at'])
            
            # Serialize message object properly
            msg = response_data.get('message')
            if msg:
                # Get fresh message instance to ensure proper serialization
                from .models import ChatMessage
                msg_obj = ChatMessage.objects.get(id=msg['id'])
                msg_serializer = ChatMessageSerializer(msg_obj)
                response_data['message'] = msg_serializer.data
            
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f'Error in chat send: {e}', exc_info=True)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChatStreamView(APIView):
    """SSE streaming endpoint — /api/chat/stream/

    Dùng Server-Sent Events (SSE) để push từng token LLM về FE ngay khi sinh ra.
    FE dùng fetch() + ReadableStream để đọc, không dùng EventSource
    (vì EventSource không support POST và auth header).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('chat_session_id')
        content = request.data.get('content', '').strip()

        if not session_id:
            return Response({'error': 'chat_session_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not content:
            return Response({'error': 'content is required'}, status=status.HTTP_400_BAD_REQUEST)

        session = get_object_or_404(ChatSession, id=session_id, user=request.user, is_deleted=False)

        document_id = request.data.get('document_id')
        document_id = int(document_id) if document_id else None
        if document_id:
            from apps.documents.models import Document
            from apps.teams.permissions import user_can_access_document
            document = Document.objects.filter(id=document_id, is_deleted=False).first()
            if not document or not user_can_access_document(request.user, document):
                return Response({'error': 'document is not available'}, status=status.HTTP_403_FORBIDDEN)

        from .chat_service import ChatService
        chat_service = ChatService()

        def event_stream():
            yield 'retry: 3000\n\n'  # FE retry sau 3s nếu connection drop
            try:
                for sse_event in chat_service.ask_question_stream(
                    session_id=session.id,
                    question=content,
                    document_id=document_id,
                ):
                    yield sse_event
            except Exception as exc:
                import json
                logger.error('ChatStreamView: unhandled error: %s', exc, exc_info=True)
                yield f'data: {json.dumps({"type": "error", "content": str(exc)[:80]})}\n\n'

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # tắt buffering ở nginx
        return response


class ChatMessageViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only chat messages"""
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get('session_id')
        if session_id:
            return ChatMessage.objects.filter(
                chat_session_id=session_id,
                chat_session__user=self.request.user,
                chat_session__is_deleted=False,
            ).order_by('created_at')
        return ChatMessage.objects.none()


class ChatFeedbackViewSet(viewsets.ModelViewSet):
    """Chat feedback management"""
    serializer_class = ChatFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatFeedback.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
