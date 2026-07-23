from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TransactionTestCase

from AkinfoluFoods.asgi import application
from users.models import CustomUser
from users.serializers import MyTokenObtainPairSerializer
from .realtime import publish_change


class RealtimeActivityTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="live-admin",
            email="live@example.com",
            password="password",
            role=CustomUser.ADMIN,
            is_active=True,
        )
        self.token = str(MyTokenObtainPairSerializer.get_token(self.user).access_token)

    def test_authenticated_client_receives_data_changes(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/activity/?token={self.token}",
                headers=[(b"origin", settings.CORS_ALLOWED_ORIGINS[0].encode())],
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await sync_to_async(publish_change)(["sales", "operations"], "test")
            message = await communicator.receive_json_from(timeout=1)
            self.assertEqual(message["resources"], ["operations", "sales"])
            self.assertEqual(message["source"], "test")
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_unauthenticated_client_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                "/ws/activity/",
                headers=[(b"origin", settings.CORS_ALLOWED_ORIGINS[0].encode())],
            )
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()
