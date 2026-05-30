import pytest

from apps.auth.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='user@example.com',
        email='user@example.com',
        password='StrongPass1!',
        first_name='Test',
        last_name='User',
    )


@pytest.fixture
def rf_request(rf, user):
    request = rf.get('/')
    request.user = user
    return request
