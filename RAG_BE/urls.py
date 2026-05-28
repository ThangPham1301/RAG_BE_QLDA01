"""
URL configuration for RAG_BE project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from apps.auth.views import email_verification_redirect_view
from apps.projects.views import ProjectViewSet
from apps.documents.views import DocumentViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'documents', DocumentViewSet, basename='document')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('verify-email', email_verification_redirect_view, name='email_verification_redirect'),

    # API v1
    path('api/auth/', include('apps.auth.urls')),
    path('api/chat/', include('apps.chatbot.urls')),
    path('api/', include(router.urls)),
]

# Serve uploaded media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
