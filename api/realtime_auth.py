from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from users.authentication import SingleSessionJWTAuthentication


@database_sync_to_async
def _user_for_token(raw_token):
    if not raw_token:
        return AnonymousUser()
    authentication = SingleSessionJWTAuthentication()
    try:
        validated = authentication.get_validated_token(raw_token)
        return authentication.get_user(validated)
    except Exception:
        return AnonymousUser()


class QueryStringJWTAuthMiddleware:
    """Authenticate a WebSocket with the same JWT/session rules as the API."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]
        scope = dict(scope)
        scope["user"] = await _user_for_token(token)
        return await self.app(scope, receive, send)
