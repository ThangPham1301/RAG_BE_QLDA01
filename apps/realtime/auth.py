from urllib.parse import parse_qs
import logging

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from apps.auth.jwt import get_token_version


logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user_from_token(token):
    if not token:
        logger.warning('Realtime auth failed: missing token')
        return AnonymousUser()
    try:
        validated = UntypedToken(token)
        user_id_claim = getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_CLAIM', 'user_id')
        user_id = validated.payload.get(user_id_claim)
        if not user_id:
            logger.warning('Realtime auth failed: token has no %s claim. payload_keys=%s', user_id_claim, list(validated.payload.keys()))
            return AnonymousUser()
        user = get_user_model().objects.get(id=user_id)
        if get_token_version(validated) != user.auth_token_version:
            logger.warning('Realtime auth failed: token was revoked for user_id=%s', user_id)
            return AnonymousUser()
        logger.debug('Realtime auth ok: user_id=%s', user_id)
        return user
    except (InvalidToken, TokenError) as exc:
        logger.warning('Realtime auth failed: invalid token: %s', exc)
        return AnonymousUser()
    except ObjectDoesNotExist:
        logger.warning('Realtime auth failed: user not found')
        return AnonymousUser()
    except Exception as exc:
        logger.warning('Realtime auth failed: unexpected error: %s', exc, exc_info=True)
        return AnonymousUser()


class JwtAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get('query_string', b'').decode())
        token = (query.get('token') or query.get('access_token') or [''])[0]
        if not token:
            logger.warning('Realtime auth middleware: websocket query has no token. query_keys=%s', list(query.keys()))
        scope['user'] = await get_user_from_token(token)
        return await self.inner(scope, receive, send)
