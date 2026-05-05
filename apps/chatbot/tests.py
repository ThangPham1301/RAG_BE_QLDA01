from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase
from unittest.mock import patch

from django.contrib.auth import get_user_model

from apps.projects.models import Project
from apps.documents.models import Document
from apps.chatbot.chat_service import ChatService
from apps.chatbot.models import ChatMessage, ChatSession, MessageContext


class ChatServiceArchitectureTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			email='chat-arch-service@example.com',
			username='chat_arch_service',
			password='test123456',
		)
		self.project = Project.objects.create(owner=self.user, name='Service Test Project')
		self.document = Document.objects.create(
			chat_session=ChatSession.objects.create(project=self.project, user=self.user, title='Document Session'),
			uploaded_by=self.user,
			title='Service Test Document',
			file=SimpleUploadedFile('service_test.txt', b'Policy content for testing'),
			file_type=Document.FileType.TXT,
			extracted_text='Policy content for testing',
			index_status=Document.IndexStatus.INDEXED,
		)
		self.session = ChatSession.objects.create(
			project=self.project,
			user=self.user,
			title='New Chat',
		)

	def test_ask_question_creates_user_assistant_and_contexts(self):
		class DummyRag:
			def answer_question(self, **kwargs):
				return {
					'answer': 'Mock answer from test',
					'raw_retrieval': [
						{
							'id': f'{self_doc_id}_0',
							'text': 'Retrieved chunk content for traceability test',
							'score': 0.91,
							'metadata': {
								'document_id': self_doc_id,
								'chunk_index': 0,
							},
						}
					],
				}

		self_doc_id = self.document.id
		service = ChatService.__new__(ChatService)
		service.rag = DummyRag()
		service.default_top_k = 3
		service.small_talk_patterns = []

		result = ChatService.ask_question(
			service,
			session_id=self.session.id,
			question='Hay tom tat noi dung chinh',
		)

		self.assertEqual(sorted(result.keys()), ['answer', 'contexts', 'message'])
		self.assertEqual(ChatMessage.objects.filter(chat_session=self.session).count(), 2)
		self.assertEqual(
			ChatMessage.objects.filter(chat_session=self.session, role=ChatMessage.Role.USER).count(),
			1,
		)
		self.assertEqual(
			ChatMessage.objects.filter(chat_session=self.session, role=ChatMessage.Role.ASSISTANT).count(),
			1,
		)

		contexts = MessageContext.objects.filter(message__chat_session=self.session)
		self.assertEqual(contexts.count(), 1)
		self.assertEqual(contexts.first().document_id, self.document.id)
		self.assertTrue(contexts.first().chunk_id)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class ChatSendMessageEndpointTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			email='chat-arch-endpoint@example.com',
			username='chat_arch_endpoint',
			password='test123456',
		)
		self.project = Project.objects.create(owner=self.user, name='Endpoint Test Project')
		self.session = ChatSession.objects.create(project=self.project, user=self.user, title='New Chat')
		self.client.force_authenticate(user=self.user)

	def test_send_message_creates_exactly_two_messages(self):
		def fake_ask_question(_service, session_id, question):
			session = ChatSession.objects.get(id=session_id)
			ChatMessage.objects.create(
				chat_session=session,
				role=ChatMessage.Role.USER,
				content=question,
			)
			assistant = ChatMessage.objects.create(
				chat_session=session,
				role=ChatMessage.Role.ASSISTANT,
				content='Endpoint test answer',
			)
			return {
				'message': {
					'id': assistant.id,
					'role': assistant.role,
					'content': assistant.content,
					'sources': [],
					'model_name': assistant.model_name,
					'created_at': assistant.created_at.isoformat(),
				},
				'answer': assistant.content,
				'contexts': [],
			}

		with patch('apps.chatbot.chat_service.ChatService.__init__', return_value=None):
			with patch('apps.chatbot.chat_service.ChatService.ask_question', new=fake_ask_question):
				response = self.client.post(
					'/api/chat/send/',
					{
						'chat_session_id': self.session.id,
						'content': 'Endpoint question',
					},
					format='json',
				)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(sorted(response.data.keys()), ['answer', 'contexts', 'message'])
		self.assertEqual(ChatMessage.objects.filter(chat_session=self.session).count(), 2)
