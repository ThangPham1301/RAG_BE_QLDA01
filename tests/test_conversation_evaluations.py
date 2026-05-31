import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.auth.models import User
from apps.chatbot.models import ChatSession, ConversationEvaluation
from apps.chatbot.views import ConversationEvaluationViewSet
from apps.projects.models import Project


@pytest.fixture
def chat_session(user):
    project = Project.objects.create(owner=user, name='RAG Project')
    return ChatSession.objects.create(project=project, user=user, title='Policy chat')


def evaluation_view(action):
    return ConversationEvaluationViewSet.as_view(action)


@pytest.mark.django_db
def test_create_evaluation_creates_one_official_record(user, chat_session, monkeypatch):
    monkeypatch.setattr(
        ConversationEvaluationViewSet,
        '_send_admin_evaluation_event',
        lambda self, event_type, data: None,
    )
    request = APIRequestFactory().post(
        '/api/chat/evaluations/',
        {'chat_session': chat_session.id, 'rating': 4, 'comment': 'Good answer'},
        format='json',
    )
    force_authenticate(request, user=user)

    response = evaluation_view({'post': 'create'})(request)

    assert response.status_code == 201
    assert ConversationEvaluation.objects.filter(chat_session=chat_session).count() == 1
    assert response.data['rating'] == 4


@pytest.mark.django_db
def test_second_evaluation_updates_existing_record_without_duplicate(user, chat_session, monkeypatch):
    evaluation = ConversationEvaluation.objects.create(
        chat_session=chat_session,
        user=user,
        rating=2,
        comment='Old',
    )
    monkeypatch.setattr(
        ConversationEvaluationViewSet,
        '_send_admin_evaluation_event',
        lambda self, event_type, data: None,
    )
    request = APIRequestFactory().post(
        '/api/chat/evaluations/',
        {'chat_session': chat_session.id, 'rating': 5, 'comment': 'Updated'},
        format='json',
    )
    force_authenticate(request, user=user)

    response = evaluation_view({'post': 'create'})(request)
    evaluation.refresh_from_db()

    assert response.status_code == 200
    assert ConversationEvaluation.objects.filter(chat_session=chat_session).count() == 1
    assert evaluation.rating == 5
    assert evaluation.comment == 'Updated'


@pytest.mark.django_db
def test_user_update_unpins_pinned_evaluation(user, chat_session, monkeypatch):
    admin = User.objects.create_user(
        username='admin@example.com',
        email='admin@example.com',
        password='StrongPass1!',
        is_staff=True,
    )
    evaluation = ConversationEvaluation.objects.create(
        chat_session=chat_session,
        user=user,
        rating=3,
        is_pinned=True,
        pinned_by=admin,
    )
    monkeypatch.setattr(
        ConversationEvaluationViewSet,
        '_send_admin_evaluation_event',
        lambda self, event_type, data: None,
    )
    request = APIRequestFactory().patch(
        f'/api/chat/evaluations/{evaluation.id}/',
        {'rating': 4},
        format='json',
    )
    force_authenticate(request, user=user)

    response = evaluation_view({'patch': 'partial_update'})(request, pk=evaluation.id)
    evaluation.refresh_from_db()

    assert response.status_code == 200
    assert evaluation.rating == 4
    assert evaluation.is_pinned is False
    assert evaluation.pinned_by is None
    assert evaluation.pinned_at is None


@pytest.mark.django_db
def test_non_admin_cannot_view_global_evaluation_stats(user):
    request = APIRequestFactory().get('/api/chat/evaluations/stats/')
    force_authenticate(request, user=user)

    response = evaluation_view({'get': 'stats'})(request)

    assert response.status_code == 403
    assert response.data['detail'] == 'Admin role is required.'
