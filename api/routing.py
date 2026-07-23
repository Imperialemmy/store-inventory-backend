from django.urls import path

from .consumers import ActivityConsumer


websocket_urlpatterns = [
    path("ws/activity/", ActivityConsumer.as_asgi()),
]
