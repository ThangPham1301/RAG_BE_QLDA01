from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatSessionViewSet, ChatSendView, ChatStreamView
from .views_new import AskQuestionView

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
	path('', include(router.urls)),
	path('send/', ChatSendView.as_view(), name='chat-send'),
	path('stream/', ChatStreamView.as_view(), name='chat-stream'),
	path('ask/', AskQuestionView.as_view(), name='ask-question'),
]


