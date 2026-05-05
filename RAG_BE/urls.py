"""
URL configuration for RAG_BE project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.projects.views import ProjectViewSet
from apps.documents.views import DocumentViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'documents', DocumentViewSet, basename='document')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/auth/', include('apps.auth.urls')),
    path('api/chat/', include('apps.chatbot.urls')),
    path('api/', include(router.urls)),
]
