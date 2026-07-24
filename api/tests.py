from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from AkinfoluFoods.asgi import application
from users.models import CustomUser
from users.serializers import MyTokenObtainPairSerializer
from .realtime import publish_change
from .realtime_auth import create_websocket_ticket


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
            ticket = await sync_to_async(create_websocket_ticket)(self.user)
            communicator = WebsocketCommunicator(
                application,
                f"/ws/activity/?ticket={ticket}",
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

    def test_api_issues_ticket_for_authenticated_user(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"JWT {self.token}")
        response = client.post("/api/v1/realtime-ticket/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ticket"])

    def test_api_rejects_unauthenticated_ticket_request(self):
        response = APIClient().post("/api/v1/realtime-ticket/")
        self.assertEqual(response.status_code, 401)

    def test_each_ticket_is_unique(self):
        first = create_websocket_ticket(self.user)
        second = create_websocket_ticket(self.user)
        self.assertNotEqual(first, second)

    def test_ticket_is_single_use(self):
        async def scenario():
            ticket = await sync_to_async(create_websocket_ticket)(self.user)
            headers = [(b"origin", settings.CORS_ALLOWED_ORIGINS[0].encode())]
            first = WebsocketCommunicator(
                application,
                f"/ws/activity/?ticket={ticket}",
                headers=headers,
            )
            connected, _ = await first.connect()
            self.assertTrue(connected)
            await first.disconnect()

            second = WebsocketCommunicator(
                application,
                f"/ws/activity/?ticket={ticket}",
                headers=headers,
            )
            connected, close_code = await second.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_access_token_in_query_string_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/activity/?token={self.token}",
                headers=[(b"origin", settings.CORS_ALLOWED_ORIGINS[0].encode())],
            )
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()
