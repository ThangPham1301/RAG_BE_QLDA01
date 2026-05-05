import logging
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatSession, ChatMessage
from .serializers import (
	ChatSessionSerializer,
	ChatSessionDetailSerializer,
	ChatMessageSerializer,
	ChatMessageCreateSerializer
)
from .chat_service import ChatService

logger = logging.getLogger(__name__)


class ChatSessionViewSet(viewsets.ViewSet):
	"""API cho ChatSession.
	
	Endpoints:
	- GET /api/chat/sessions/ → list all sessions
	- POST /api/chat/sessions/ → create session
	- GET /api/chat/sessions/{id}/ → get session detail with messages
	- DELETE /api/chat/sessions/{id}/ → archive session (soft delete)
	"""
	
	def list(self, request):
		"""List sessions của user (filter by project_id nếu có)."""
		logger.info('[ChatSessionViewSet.list] Request received')
		
		project_id = request.query_params.get('project_id')
		
		if not project_id:
			return Response(
				{'error': 'project_id là bắt buộc'},
				status=status.HTTP_400_BAD_REQUEST
			)
		
		sessions = ChatSession.objects.filter(
			project_id=project_id,
			is_archived=False
		).order_by('-updated_at')
		
		serializer = ChatSessionSerializer(sessions, many=True)
		return Response({
			'count': sessions.count(),
			'results': serializer.data
		})
	
	def create(self, request):
		"""Tạo session mới."""
		logger.info('[ChatSessionViewSet.create] Request received')
		
		project_id = request.data.get('project_id')
		title = request.data.get('title')
		
		if not project_id:
			return Response(
				{'error': 'project_id là bắt buộc'},
				status=status.HTTP_400_BAD_REQUEST
			)
		
		try:
			chat_service = ChatService()
			session = chat_service.create_session(project_id, title)
			
			serializer = ChatSessionSerializer(session)
			return Response(serializer.data, status=status.HTTP_201_CREATED)
		
		except Exception as exc:
			logger.error(f'[ChatSessionViewSet.create] Error: {exc}', exc_info=True)
			return Response(
				{'error': str(exc)},
				status=status.HTTP_500_INTERNAL_SERVER_ERROR
			)
	
	def retrieve(self, request, pk=None):
		"""Lấy session detail + messages."""
		logger.info(f'[ChatSessionViewSet.retrieve] session_id={pk}')
		
		try:
			session = ChatSession.objects.get(id=pk)
			serializer = ChatSessionDetailSerializer(session)
			return Response(serializer.data)
		except ChatSession.DoesNotExist:
			return Response(
				{'error': f'Session {pk} không tồn tại'},
				status=status.HTTP_404_NOT_FOUND
			)
	
	def destroy(self, request, pk=None):
		"""Archive session (soft delete)."""
		logger.info(f'[ChatSessionViewSet.destroy] session_id={pk}')
		
		try:
			session = ChatSession.objects.get(id=pk)
			session.is_archived = True
			session.save()
			
			return Response(
				{'message': 'Session đã được lưu trữ'},
				status=status.HTTP_204_NO_CONTENT
			)
		except ChatSession.DoesNotExist:
			return Response(
				{'error': f'Session {pk} không tồn tại'},
				status=status.HTTP_404_NOT_FOUND
			)


class ChatMessageViewSet(viewsets.ViewSet):
	"""API cho ChatMessage.
	
	Endpoints:
	- GET /api/chat/session/{session_id}/messages/ → get messages
	- POST /api/chat/ask/ → ask question (create user + assistant message)
	"""
	
	def list(self, request, session_id=None):
		"""Lấy messages của session."""
		logger.info(f'[ChatMessageViewSet.list] session_id={session_id}')
		
		if not session_id:
			return Response(
				{'error': 'session_id là bắt buộc'},
				status=status.HTTP_400_BAD_REQUEST
			)
		
		try:
			session = ChatSession.objects.get(id=session_id)
		except ChatSession.DoesNotExist:
			return Response(
				{'error': f'Session {session_id} không tồn tại'},
				status=status.HTTP_404_NOT_FOUND
			)
		
		messages = session.messages.all().order_by('created_at')
		serializer = ChatMessageSerializer(messages, many=True)
		
		return Response({
			'count': messages.count(),
			'session_id': session_id,
			'results': serializer.data
		})


class AskQuestionView(APIView):
	"""Endpoint hỏi đáp - tạo user message + assistant message + save sources.
	
	POST /api/chat/ask/
	{
		"session_id": 12,
		"question": "Hạn nộp hồ sơ?"
	}
	"""
	
	def post(self, request):
		logger.info('[AskQuestionView] POST request received')
		
		serializer = ChatMessageCreateSerializer(data=request.data)
		if not serializer.is_valid():
			return Response(
				serializer.errors,
				status=status.HTTP_400_BAD_REQUEST
			)
		
		session_id = serializer.validated_data['session_id']
		question = serializer.validated_data['question']
		
		logger.info(f'[AskQuestionView] session_id={session_id}, question={question[:50]}')
		
		try:
			chat_service = ChatService()
			result = chat_service.ask_question(session_id, question)
			
			return Response(result, status=status.HTTP_200_OK)
		
		except ValueError as exc:
			logger.warning(f'[AskQuestionView] Validation error: {exc}')
			return Response(
				{'error': str(exc)},
				status=status.HTTP_400_BAD_REQUEST
			)
		except Exception as exc:
			logger.error(f'[AskQuestionView] Error: {exc}', exc_info=True)
			return Response(
				{'error': str(exc)},
				status=status.HTTP_500_INTERNAL_SERVER_ERROR
			)
