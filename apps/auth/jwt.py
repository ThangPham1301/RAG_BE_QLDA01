from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def get_token_version(token):
    """Return token auth version, treating old tokens as version 0."""
    try:
        return int(token.get('token_version', 0))
    except (TypeError, ValueError):
        return -1


def validate_token_version(user, token):
    """Reject tokens that were issued before the user's latest auth reset."""
    if get_token_version(token) != user.auth_token_version:
        raise AuthenticationFailed(
            'Your session has expired. Please log in again.',
            code='token_revoked'
        )


class TokenVersionJWTAuthentication(JWTAuthentication):
    """JWT authentication that invalidates old tokens after password changes."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        validate_token_version(user, validated_token)
        return user
