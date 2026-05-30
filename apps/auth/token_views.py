from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenRefreshView

from .jwt import validate_token_version


class TokenVersionRefreshSerializer(TokenRefreshSerializer):
    """Refresh serializer that refuses refresh tokens invalidated by password changes."""

    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)

        if not user_id:
            raise AuthenticationFailed('Invalid refresh token.', code='token_not_valid')

        User = get_user_model()
        try:
            user = User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except User.DoesNotExist as exc:
            raise AuthenticationFailed('User not found.', code='user_not_found') from exc

        validate_token_version(user, refresh)
        return super().validate(attrs)


class TokenVersionRefreshView(TokenRefreshView):
    serializer_class = TokenVersionRefreshSerializer
