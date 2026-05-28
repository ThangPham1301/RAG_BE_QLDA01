from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ChatDocumentAttachmentView, NotificationViewSet, SharedLibraryView, TeamInvitationViewSet, TeamViewSet
from apps.projects.views import statistics_export_view


router = DefaultRouter()
router.register(r'teams', TeamViewSet, basename='team')
router.register(r'team-invitations', TeamInvitationViewSet, basename='team-invitation')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/export/', statistics_export_view, name='dashboard-statistics-export-fallback'),
    path('chat/attach-documents/', ChatDocumentAttachmentView.as_view(), name='chat-attach-documents'),
    path('library/shared/', SharedLibraryView.as_view(), name='shared-library'),
]
