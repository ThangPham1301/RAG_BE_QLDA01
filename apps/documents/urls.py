from django.urls import path

from .views import DocumentIndexView, DocumentUploadView, ProjectDocumentsListView

urlpatterns = [
	path('documents/upload/', DocumentUploadView.as_view(), name='document-upload'),
	path('projects/<int:project_id>/documents/upload/', DocumentUploadView.as_view(), name='project-document-upload'),
	path('documents/<int:pk>/index/', DocumentIndexView.as_view(), name='document-index'),
	path('projects/<int:project_id>/documents/', ProjectDocumentsListView.as_view(), name='project-documents-list'),
]
