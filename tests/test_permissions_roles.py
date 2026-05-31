import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.auth.models import User
from apps.auth.views import admin_user_role_view, admin_users_view


@pytest.mark.django_db
def test_regular_user_cannot_access_superadmin_user_management(user):
    request = APIRequestFactory().get('/api/auth/admin/users')
    force_authenticate(request, user=user)

    response = admin_users_view(request)

    assert response.status_code == 403
    assert response.data['detail'] == 'Superadmin role is required.'


@pytest.mark.django_db
def test_admin_cannot_access_superadmin_user_management(db):
    admin = User.objects.create_user(
        username='admin@example.com',
        email='admin@example.com',
        password='StrongPass1!',
        is_staff=True,
    )
    request = APIRequestFactory().get('/api/auth/admin/users')
    force_authenticate(request, user=admin)

    response = admin_users_view(request)

    assert response.status_code == 403
    assert response.data['detail'] == 'Superadmin role is required.'


@pytest.mark.django_db
def test_superadmin_can_list_users_and_assign_admin_role(user):
    superadmin = User.objects.create_superuser(
        username='root@example.com',
        email='root@example.com',
        password='StrongPass1!',
    )
    list_request = APIRequestFactory().get('/api/auth/admin/users')
    force_authenticate(list_request, user=superadmin)

    list_response = admin_users_view(list_request)

    assert list_response.status_code == 200
    assert any(item['email'] == user.email for item in list_response.data)

    role_request = APIRequestFactory().patch(
        f'/api/auth/admin/users/{user.id}/role',
        {'role': 'admin'},
        format='json',
    )
    force_authenticate(role_request, user=superadmin)

    role_response = admin_user_role_view(role_request, user.id)
    user.refresh_from_db()

    assert role_response.status_code == 200
    assert user.is_staff is True
    assert role_response.data['role'] == 'admin'


@pytest.mark.django_db
def test_superadmin_cannot_change_own_or_root_role():
    superadmin = User.objects.create_superuser(
        username='root@example.com',
        email='root@example.com',
        password='StrongPass1!',
    )
    request = APIRequestFactory().patch(
        f'/api/auth/admin/users/{superadmin.id}/role',
        {'role': 'user'},
        format='json',
    )
    force_authenticate(request, user=superadmin)

    response = admin_user_role_view(request, superadmin.id)
    superadmin.refresh_from_db()

    assert response.status_code == 400
    assert superadmin.is_superuser is True
