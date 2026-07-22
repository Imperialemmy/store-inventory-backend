from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import CustomUser


def signup(client, username, **extra):
    payload = {
        "username": username,
        "email": f"{username}@a.com",
        "password": "Str0ngPass!23",
        "first_name": "T",
        "last_name": "U",
    }
    payload.update(extra)
    return client.post("/api/v1/auth/users/", payload, format="json")


@override_settings(ADMIN_SIGNUP_CODE="SECRET123")
class SignupGateTests(TestCase):
    def test_first_user_bootstraps_as_active_admin(self):
        res = signup(APIClient(), "owner")
        self.assertEqual(res.status_code, 201)
        user = CustomUser.objects.get(username="owner")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_active)

    def test_seller_signup_is_pending(self):
        signup(APIClient(), "owner")  # first = admin
        res = signup(APIClient(), "seller1")
        self.assertEqual(res.status_code, 201)
        user = CustomUser.objects.get(username="seller1")
        self.assertEqual(user.role, "seller")
        self.assertFalse(user.is_active)

    def test_correct_admin_code_creates_active_admin(self):
        signup(APIClient(), "owner")
        signup(APIClient(), "coadmin", admin_code="SECRET123")
        user = CustomUser.objects.get(username="coadmin")
        self.assertEqual(user.role, "admin")
        self.assertTrue(user.is_active)

    def test_wrong_admin_code_is_rejected(self):
        signup(APIClient(), "owner")
        res = signup(APIClient(), "faker", admin_code="nope")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(CustomUser.objects.filter(username="faker").exists())

    def test_pending_seller_cannot_get_token(self):
        signup(APIClient(), "owner")
        signup(APIClient(), "seller1")
        res = APIClient().post("/api/v1/auth/jwt/create/",
                               {"username": "seller1", "password": "Str0ngPass!23"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_admin_approves_seller_who_can_then_log_in(self):
        signup(APIClient(), "owner")
        signup(APIClient(), "seller1")
        admin = CustomUser.objects.get(username="owner")
        seller = CustomUser.objects.get(username="seller1")
        admin_client = APIClient()
        admin_client.force_authenticate(admin)
        res = admin_client.post(f"/api/v1/users/{seller.id}/approve/")
        self.assertEqual(res.status_code, 200)
        seller.refresh_from_db()
        self.assertTrue(seller.is_active)
        token = APIClient().post("/api/v1/auth/jwt/create/",
                                 {"username": "seller1", "password": "Str0ngPass!23"}, format="json")
        self.assertEqual(token.status_code, 200)


@override_settings(ADMIN_SIGNUP_CODE="SECRET123")
class SingleSessionTests(TestCase):
    def _login(self, username, password="Str0ngPass!23"):
        return APIClient().post(
            "/api/v1/auth/jwt/create/",
            {"username": username, "password": password}, format="json").json()

    def test_new_login_invalidates_previous_session(self):
        signup(APIClient(), "owner")
        first = self._login("owner")
        client_a = APIClient()
        client_a.credentials(HTTP_AUTHORIZATION=f"JWT {first['access']}")
        self.assertEqual(client_a.get("/api/v1/products/").status_code, 200)

        # Second login from another device kicks the first one out.
        second = self._login("owner")
        res = client_a.get("/api/v1/products/")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json().get("code"), "session_replaced")

        client_b = APIClient()
        client_b.credentials(HTTP_AUTHORIZATION=f"JWT {second['access']}")
        self.assertEqual(client_b.get("/api/v1/products/").status_code, 200)


class PasswordResetEndpointTests(TestCase):
    def test_reset_password_endpoint_accepts_email(self):
        signup(APIClient(), "owner")
        res = APIClient().post(
            "/api/v1/auth/users/reset_password/",
            {"email": "owner@a.com"}, format="json")
        self.assertEqual(res.status_code, 204)
