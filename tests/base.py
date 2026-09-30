from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.service_requests.models import Category

PASSWORD = "Str0ng!Pass99"


def make_user(email, role=Role.CITIZEN, phone="+8801710000000", name="Test User"):
    return User.objects.create_user(email=email, password=PASSWORD, phone=phone, full_name=name, role=role)


class BaseAPITest(APITestCase):
    def setUp(self):
        cache.clear()  # rate-limit counters live in the cache
        self.admin = make_user("admin@t.com", Role.ADMIN, "+8801710000001", "Admin")
        self.officer = make_user("off1@t.com", Role.OFFICER, "+8801710000002", "Officer One")
        self.officer2 = make_user("off2@t.com", Role.OFFICER, "+8801710000003", "Officer Two")
        self.citizen = make_user("cit@t.com", Role.CITIZEN, "+8801710000004", "Citizen One")
        self.other = make_user("cit2@t.com", Role.CITIZEN, "+8801710000005", "Citizen Two")
        self.category = Category.objects.create(name="NID Request")

    def as_user(self, user):
        self.client.force_authenticate(user)

    def new_request(self, citizen=None, priority="medium", **extra):
        self.as_user(citizen or self.citizen)
        payload = {"category": self.category.id, "title": "Need NID", "description": "Lost my card", "priority": priority}
        payload.update(extra)
        res = self.client.post("/api/requests/", payload, format="json")
        assert res.status_code == 201, res.content
        return res.data["id"]

    def call(self, user, method, url, data=None, fmt="json"):
        self.as_user(user)
        return getattr(self.client, method)(url, data, format=fmt)

    def complete_flow(self, priority, officer=None):
        officer = officer or self.officer
        rid = self.new_request(priority=priority)
        assert self.call(self.admin, "post", f"/api/requests/{rid}/validate/").status_code == 200
        assert self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": officer.id}).status_code == 200
        assert self.call(officer, "post", f"/api/requests/{rid}/status/", {"status": "pending"}).status_code == 200
        assert self.call(officer, "post", f"/api/requests/{rid}/status/", {"status": "task_done"}).status_code == 200
        return rid
