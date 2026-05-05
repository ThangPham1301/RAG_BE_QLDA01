from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.chatbot.models import ChatSession
from apps.documents.models import Document
from apps.projects.models import Project


class ProjectStatisticsEndpointTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			email='projects-stats@example.com',
			username='projects_stats',
			password='test123456',
		)
		self.other_user = user_model.objects.create_user(
			email='projects-stats-other@example.com',
			username='projects_stats_other',
			password='test123456',
		)
		self.project = Project.objects.create(owner=self.user, name='Stats Project')
		self.other_project = Project.objects.create(owner=self.other_user, name='Other Stats Project')

		self.chat_session = ChatSession.objects.create(project=self.project, user=self.user, title='Stats Chat')
		ChatSession.objects.create(project=self.project, user=self.user, title='Archived Chat', is_archived=True)
		ChatSession.objects.create(project=self.other_project, user=self.other_user, title='Other User Chat')

		Document.objects.create(
<<<<<<< HEAD
			project=self.project,
			uploaded_by=self.user,
			uploaded_chat_session=self.chat_session,
=======
			chat_session=self.chat_session,
			uploaded_by=self.user,
>>>>>>> 5f5f0ac (fix chat structure)
			title='Indexed Doc',
			file=SimpleUploadedFile('indexed.txt', b'Indexed content', content_type='text/plain'),
			file_type=Document.FileType.TXT,
			index_status=Document.IndexStatus.INDEXED,
			indexed_chunks=8,
		)
		Document.objects.create(
<<<<<<< HEAD
			project=self.project,
=======
			chat_session=self.chat_session,
>>>>>>> 5f5f0ac (fix chat structure)
			uploaded_by=self.user,
			title='Failed Doc',
			file=SimpleUploadedFile('failed.txt', b'Failed content', content_type='text/plain'),
			file_type=Document.FileType.TXT,
			index_status=Document.IndexStatus.FAILED,
			indexed_chunks=0,
		)
		Document.objects.create(
<<<<<<< HEAD
			project=self.other_project,
=======
			chat_session=ChatSession.objects.create(project=self.other_project, user=self.other_user, title='Other Doc Chat'),
>>>>>>> 5f5f0ac (fix chat structure)
			uploaded_by=self.other_user,
			title='Other User Doc',
			file=SimpleUploadedFile('other.txt', b'Other content', content_type='text/plain'),
			file_type=Document.FileType.TXT,
			index_status=Document.IndexStatus.INDEXED,
			indexed_chunks=99,
		)

		self.client.force_authenticate(user=self.user)

	def test_statistics_returns_user_scoped_aggregates(self):
		response = self.client.get('/api/projects/statistics/')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['total_projects'], 1)
		self.assertEqual(response.data['total_documents'], 2)
		self.assertEqual(response.data['indexed_documents'], 1)
		self.assertEqual(response.data['failed_documents'], 1)
		self.assertEqual(response.data['total_indexed_chunks'], 8)
		self.assertEqual(response.data['active_chat_sessions'], 1)
		self.assertGreaterEqual(len(response.data['recent_uploads']), 1)
		self.assertEqual(response.data['recent_uploads'][0]['project_id'], self.project.id)
