from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatSessionViewSet, AskQuestionView

router = DefaultRouter()
router.register(r'sessions', ChatSessionViewSet, basename='chat-session')

urlpatterns = [
	path('', include(router.urls)),
	path('ask/', AskQuestionView.as_view(), name='ask-question'),
]

