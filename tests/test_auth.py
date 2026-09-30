from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

from .base import PASSWORD, BaseAPITest

REG = {"email": "New@Example.com", "phone": "+8801799999999", "full_name": "New Person", "password": "Str0ng!Pass99"}


class AuthTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_register_creates_citizen_and_returns_tokens(self):
        res = self.client.post("/api/auth/register/", {**REG, "role": "admin"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertIn("access", res.data)
        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.role, Role.CITIZEN)  # role in payload is ignored

    def test_duplicate_email_or_phone_rejected(self):
        self.client.post("/api/auth/register/", REG, format="json")
        again = self.client.post("/api/auth/register/", {**REG, "email": "new@example.com", "phone": "+8801711111111"}, format="json")
        self.assertEqual(again.status_code, 400)
        same_phone = self.client.post("/api/auth/register/", {**REG, "email": "z@example.com"}, format="json")
        self.assertEqual(same_phone.status_code, 400)

    def test_weak_password_and_bad_phone_rejected(self):
        self.assertEqual(self.client.post("/api/auth/register/", {**REG, "password": "12345678"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/register/", {**REG, "phone": "abc"}, format="json").status_code, 400)

    def test_login_and_me(self):
        res = self.client.post("/api/auth/login/", {"email": "CIT@t.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["user"]["role"], "citizen")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + res.data["access"])
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.data["email"], "cit@t.com")

    def test_wrong_password_and_anonymous_access(self):
        self.assertEqual(self.client.post("/api/auth/login/", {"email": "cit@t.com", "password": "nope"}, format="json").status_code, 401)
        self.assertEqual(self.client.get("/api/requests/").status_code, 401)

    def test_refresh_token(self):
        res = self.client.post("/api/auth/login/", {"email": "cit@t.com", "password": PASSWORD}, format="json")
        new = self.client.post("/api/auth/refresh/", {"refresh": res.data["refresh"]}, format="json")
        self.assertEqual(new.status_code, 200)
        self.assertIn("access", new.data)


class RateLimitTests(BaseAPITest):
    @override_settings(RATE_LIMIT_AUTH_PER_MIN=5)
    def test_login_blocked_after_limit(self):
        codes = [self.client.post("/api/auth/login/", {"email": "cit@t.com", "password": "bad"}, format="json").status_code for _ in range(7)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5:], [429, 429])

    @override_settings(RATE_LIMIT_AUTH_PER_MIN=5)
    def test_429_has_retry_after_and_valid_login_also_blocked(self):
        for _ in range(5):
            self.client.post("/api/auth/login/", {"email": "cit@t.com", "password": "bad"}, format="json")
        res = self.client.post("/api/auth/login/", {"email": "cit@t.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 429)
        self.assertIn("Retry-After", res)

    def test_default_auth_limit_is_50(self):
        from django.conf import settings
        self.assertEqual(settings.RATE_LIMIT_AUTH_PER_MIN, 50)

    @override_settings(RATE_LIMIT_API_PER_MIN=3)
    def test_api_limit_is_per_user(self):
        self.as_user(self.citizen)
        codes = [self.client.get("/api/requests/").status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.as_user(self.other)  # a different user has their own bucket
        self.assertEqual(self.client.get("/api/requests/").status_code, 200)
