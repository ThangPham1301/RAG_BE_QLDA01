"""
URL configuration for RAG_BE project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.projects.views import ProjectViewSet
from apps.documents.views import DocumentViewSet
from apps.chatbot.views import ChatSessionViewSet, ChatMessageViewSet, ChatFeedbackViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'chat/sessions', ChatSessionViewSet, basename='chat-session')
router.register(r'chat/messages', ChatMessageViewSet, basename='chat-message')
router.register(r'chat/feedback', ChatFeedbackViewSet, basename='chat-feedback')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/auth/', include('apps.auth.urls')),
    path('api/', include(router.urls)),
]
