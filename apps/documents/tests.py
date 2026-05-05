from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.chatbot.models import ChatSession
from apps.documents.models import Document
from apps.projects.models import Project


class DocumentUploadFlowTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			email='documents-tests@example.com',
			username='documents_tests',
			password='test123456',
		)
		self.other_user = user_model.objects.create_user(
			email='documents-tests-other@example.com',
			username='documents_tests_other',
			password='test123456',
		)
		self.project = Project.objects.create(owner=self.user, name='Project Documents')
		self.other_project = Project.objects.create(owner=self.other_user, name='Other Project')
		self.chat_session = ChatSession.objects.create(project=self.project, user=self.user, title='Chat Upload')
		self.other_chat_session = ChatSession.objects.create(project=self.other_project, user=self.other_user, title='Other Chat')
		self.client.force_authenticate(user=self.user)

	@patch('apps.documents.views.DocumentViewSet._schedule_indexing')
	def test_upload_document_with_chat_session_link(self, _mock_indexing):
		file_obj = SimpleUploadedFile('notes.txt', b'Project upload content', content_type='text/plain')

		response = self.client.post(
			'/api/documents/',
			{
<<<<<<< HEAD
				'project': self.project.id,
=======
>>>>>>> 5f5f0ac (fix chat structure)
				'chat_session': self.chat_session.id,
				'file': file_obj,
				'title': 'Meeting Notes',
			},
			format='multipart',
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['uploaded_count'], 1)
		created_id = response.data['documents'][0]['id']
		document = Document.objects.get(id=created_id)
<<<<<<< HEAD
		self.assertEqual(document.uploaded_chat_session_id, self.chat_session.id)
		self.assertEqual(document.project_id, self.project.id)
=======
		self.assertEqual(document.chat_session_id, self.chat_session.id)
		self.assertEqual(document.chat_session.project_id, self.project.id)
>>>>>>> 5f5f0ac (fix chat structure)

	@patch('apps.documents.views.DocumentViewSet._schedule_indexing')
	def test_upload_rejects_chat_session_outside_project(self, _mock_indexing):
		file_obj = SimpleUploadedFile('notes.txt', b'Invalid session relation', content_type='text/plain')

		response = self.client.post(
			'/api/documents/',
			{
<<<<<<< HEAD
				'project': self.project.id,
=======
>>>>>>> 5f5f0ac (fix chat structure)
				'chat_session': self.other_chat_session.id,
				'file': file_obj,
				'title': 'Invalid Link',
			},
			format='multipart',
		)

		self.assertEqual(response.status_code, 400)
<<<<<<< HEAD
		self.assertIn('uploaded_chat_session', str(response.data))
=======
		self.assertIn('chat_session', str(response.data))
>>>>>>> 5f5f0ac (fix chat structure)
