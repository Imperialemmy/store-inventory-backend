import hashlib
import secrets
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.core.cache import cache


TICKET_SALT = "akinfolu.websocket.activity"
TICKET_MAX_AGE_SECONDS = 30
TICKET_USED_PREFIX = "ws-ticket-used:"


def create_websocket_ticket(user):
    """Create a short-lived credential that cannot be used for API calls."""
    return signing.dumps(
        {
            "user_id": user.pk,
            "sid": str(user.session_id),
            "nonce": secrets.token_urlsafe(16),
        },
        key=settings.SECRET_KEY,
        salt=TICKET_SALT,
        compress=True,
    )


@database_sync_to_async
def _user_for_ticket(ticket):
    if not ticket:
        return AnonymousUser()
    try:
        payload = signing.loads(
            ticket,
            key=settings.SECRET_KEY,
            salt=TICKET_SALT,
            max_age=TICKET_MAX_AGE_SECONDS,
        )
        user_id = payload["user_id"]
        session_id = str(payload["sid"])
    except (KeyError, TypeError, signing.BadSignature, signing.SignatureExpired):
        return AnonymousUser()

    digest = hashlib.sha256(ticket.encode()).hexdigest()
    if not cache.add(
        f"{TICKET_USED_PREFIX}{digest}",
        True,
        timeout=TICKET_MAX_AGE_SECONDS,
    ):
        return AnonymousUser()

    user_model = get_user_model()
    try:
        user = user_model.objects.get(pk=user_id, is_active=True)
    except user_model.DoesNotExist:
        return AnonymousUser()
    if str(user.session_id) != session_id:
        return AnonymousUser()
    return user


class WebSocketTicketAuthMiddleware:
    """Authenticate a WebSocket using a short-lived, single-use ticket."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = query.get("ticket", [None])[0]
        scope = dict(scope)
        scope["user"] = await _user_for_ticket(ticket)
        return await self.app(scope, receive, send)
