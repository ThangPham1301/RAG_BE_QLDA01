"""
URL configuration for RAG_BE project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from apps.projects.views import ProjectViewSet, statistics_export_view
from apps.documents.views import DocumentViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'documents', DocumentViewSet, basename='document')

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/dashboard/export/', statistics_export_view, name='dashboard-statistics-export'),
    path('api/projects/statistics-export/', statistics_export_view, name='project-statistics-export'),
    path('api/statistics-export/', statistics_export_view, name='project-statistics-export-legacy'),
    path('api/auth/', include('apps.auth.urls')),
    path('api/chat/', include('apps.chatbot.urls')),
    path('api/', include('apps.teams.urls')),
    path('api/', include(router.urls)),
]

# Serve uploaded media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
