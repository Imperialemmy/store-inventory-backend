"""
ASGI config for AkinfoluFoods project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AkinfoluFoods.settings')

django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from api.realtime_auth import QueryStringJWTAuthMiddleware
from api.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_application,
    "websocket": OriginValidator(
        QueryStringJWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
        settings.CORS_ALLOWED_ORIGINS,
    ),
})
