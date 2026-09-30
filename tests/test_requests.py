import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.accounts.models import User
from apps.service_requests.models import Category

from .base import BaseAPITest


class RequestFlowTests(BaseAPITest):
    def test_citizen_creates_request_with_remarks_and_default_status(self):
        rid = self.new_request(priority="high", remarks="Urgent, flight next week")
        res = self.call(self.citizen, "get", f"/api/requests/{rid}/")
        self.assertEqual(res.data["status"], "not_validated")
        self.assertEqual(res.data["remarks"], "Urgent, flight next week")
        self.assertEqual(res.data["priority"], "high")

    def test_citizen_cannot_set_status_or_officer_on_create(self):
        rid = self.new_request(status="task_done", officer=self.officer.id)
        res = self.call(self.citizen, "get", f"/api/requests/{rid}/")
        self.assertEqual(res.data["status"], "not_validated")
        self.assertIsNone(res.data["officer"])

    def test_only_citizens_can_create(self):
        payload = {"category": self.category.id, "title": "x", "description": "y"}
        for user in (self.admin, self.officer):
            self.assertEqual(self.call(user, "post", "/api/requests/", payload).status_code, 403)

    def test_inactive_category_rejected(self):
        inactive = Category.objects.create(name="Old", is_active=False)
        res = self.call(self.citizen, "post", "/api/requests/", {"category": inactive.id, "title": "x", "description": "y"})
        self.assertEqual(res.status_code, 400)

    def test_visibility_is_scoped_by_role(self):
        rid = self.new_request()
        self.assertEqual(self.call(self.other, "get", "/api/requests/").data["count"], 0)
        self.assertEqual(self.call(self.other, "get", f"/api/requests/{rid}/").status_code, 404)
        self.assertEqual(self.call(self.officer, "get", "/api/requests/").data["count"], 0)
        self.assertEqual(self.call(self.admin, "get", "/api/requests/").data["count"], 1)

    def test_citizen_can_edit_only_before_validation(self):
        rid = self.new_request()
        ok = self.call(self.citizen, "patch", f"/api/requests/{rid}/", {"title": "Better title"})
        self.assertEqual(ok.status_code, 200)
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        late = self.call(self.citizen, "patch", f"/api/requests/{rid}/", {"title": "Too late"})
        self.assertEqual(late.status_code, 409)
        stranger = self.call(self.other, "patch", f"/api/requests/{rid}/", {"title": "Hack"})
        self.assertEqual(stranger.status_code, 404)

    def test_full_lifecycle(self):
        rid = self.new_request()
        self.assertEqual(self.call(self.admin, "post", f"/api/requests/{rid}/validate/").data["status"], "validated")
        assigned = self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        self.assertEqual(assigned.data["status"], "officer_assigned")
        self.assertEqual(assigned.data["officer"], self.officer.id)
        self.assertEqual(self.call(self.officer, "post", f"/api/requests/{rid}/status/", {"status": "pending"}).data["status"], "pending")
        self.assertEqual(self.call(self.officer, "post", f"/api/requests/{rid}/status/", {"status": "task_done"}).data["status"], "task_done")
        self.assertEqual(self.call(self.citizen, "get", f"/api/requests/{rid}/").data["status_label"], "Task done")

    def test_role_restrictions_on_workflow_actions(self):
        rid = self.new_request()
        self.assertEqual(self.call(self.citizen, "post", f"/api/requests/{rid}/validate/").status_code, 403)
        self.assertEqual(self.call(self.officer, "post", f"/api/requests/{rid}/validate/").status_code, 403)
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        self.assertEqual(self.call(self.citizen, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id}).status_code, 403)

    def test_cannot_skip_steps(self):
        rid = self.new_request()
        # cannot assign before validation
        self.assertEqual(self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id}).status_code, 409)
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        # cannot jump straight to done
        self.assertEqual(self.call(self.officer, "post", f"/api/requests/{rid}/status/", {"status": "task_done"}).status_code, 409)
        # validating twice is invalid
        self.assertEqual(self.call(self.admin, "post", f"/api/requests/{rid}/validate/").status_code, 409)

    def test_officer_cannot_touch_someone_elses_task(self):
        rid = self.new_request()
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        res = self.call(self.officer2, "post", f"/api/requests/{rid}/status/", {"status": "pending"})
        self.assertEqual(res.status_code, 404)  # not even visible

    def test_assign_rejects_non_officer(self):
        rid = self.new_request()
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        res = self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.other.id})
        self.assertEqual(res.status_code, 400)


class AvailabilityTests(BaseAPITest):
    @override_settings(OFFICER_MAX_ACTIVE_TASKS=2)
    def test_dropdown_lists_only_available_officers(self):
        ids = lambda: [o["id"] for o in self.call(self.admin, "get", "/api/admin/officers/available/").data]
        self.assertCountEqual(ids(), [self.officer.id, self.officer2.id])
        for _ in range(2):
            rid = self.new_request()
            self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
            self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        self.assertEqual(ids(), [self.officer2.id])  # officer 1 is full
        # server-side guard, not just the dropdown
        rid = self.new_request()
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        res = self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        self.assertEqual(res.status_code, 409)

    @override_settings(OFFICER_MAX_ACTIVE_TASKS=1)
    def test_officer_becomes_available_again_after_finishing(self):
        self.complete_flow("low")
        avail = [o["id"] for o in self.call(self.admin, "get", "/api/admin/officers/available/").data]
        self.assertIn(self.officer.id, avail)

    def test_only_admin_sees_available_list(self):
        self.assertEqual(self.call(self.citizen, "get", "/api/admin/officers/available/").status_code, 403)


class PointsTests(BaseAPITest):
    def test_points_by_priority(self):
        self.complete_flow("high")
        self.complete_flow("medium")
        self.complete_flow("low")
        self.officer.refresh_from_db()
        self.assertEqual(self.officer.points, 3 + 2 + 1)

    def test_points_only_go_to_assigned_officer_and_only_once(self):
        rid = self.complete_flow("high")
        self.officer2.refresh_from_db()
        self.assertEqual(self.officer2.points, 0)
        again = self.call(self.officer, "post", f"/api/requests/{rid}/status/", {"status": "task_done"})
        self.assertEqual(again.status_code, 409)
        self.officer.refresh_from_db()
        self.assertEqual(self.officer.points, 3)
        self.assertEqual(self.call(self.citizen, "get", f"/api/requests/{rid}/").data["points_awarded"], 3)


class CommentTests(BaseAPITest):
    def test_admin_comment_audiences(self):
        rid = self.new_request()
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        self.call(self.admin, "post", f"/api/requests/{rid}/comments/", {"body": "Please bring original NID", "audience": "citizen"})
        self.call(self.admin, "post", f"/api/requests/{rid}/comments/", {"body": "Priority case, handle today", "audience": "officer"})
        citizen_view = [c["body"] for c in self.call(self.citizen, "get", f"/api/requests/{rid}/comments/").data]
        officer_view = [c["body"] for c in self.call(self.officer, "get", f"/api/requests/{rid}/comments/").data]
        self.assertEqual(citizen_view, ["Please bring original NID"])
        self.assertEqual(len(officer_view), 2)

    def test_citizen_cannot_write_internal_comment_or_comment_on_others(self):
        rid = self.new_request()
        res = self.call(self.citizen, "post", f"/api/requests/{rid}/comments/", {"body": "secret", "audience": "officer"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.call(self.other, "post", f"/api/requests/{rid}/comments/", {"body": "hi"}).status_code, 404)
        ok = self.call(self.citizen, "post", f"/api/requests/{rid}/comments/", {"body": "Any update?"})
        self.assertEqual(ok.status_code, 201)


class AttachmentTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)

    def upload(self, user, rid, name="doc.pdf", content=b"%PDF-1.4 test"):
        with override_settings(MEDIA_ROOT=self.media):
            self.as_user(user)
            return self.client.post(f"/api/requests/{rid}/attachments/", {"file": SimpleUploadedFile(name, content)}, format="multipart")

    def test_upload_list_and_download(self):
        rid = self.new_request()
        res = self.upload(self.citizen, rid)
        self.assertEqual(res.status_code, 201)
        with override_settings(MEDIA_ROOT=self.media):
            listing = self.call(self.citizen, "get", f"/api/requests/{rid}/attachments/")
            self.assertEqual(len(listing.data), 1)
            download = self.call(self.citizen, "get", listing.data[0]["download_url"])
            self.assertEqual(download.status_code, 200)
            self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4 test")
            self.assertEqual(self.call(self.other, "get", listing.data[0]["download_url"]).status_code, 404)

    def test_bad_extension_and_size_rejected(self):
        rid = self.new_request()
        self.assertEqual(self.upload(self.citizen, rid, "virus.exe").status_code, 400)
        with override_settings(MAX_UPLOAD_MB=0):
            self.assertEqual(self.upload(self.citizen, rid, "a.pdf", b"x" * 10).status_code, 400)


class AdminTests(BaseAPITest):
    def test_stats_and_officer_overview(self):
        self.complete_flow("high")
        rid = self.new_request(priority="low")
        self.call(self.admin, "post", f"/api/requests/{rid}/validate/")
        self.call(self.admin, "post", f"/api/requests/{rid}/assign/", {"officer_id": self.officer.id})
        stats = self.call(self.admin, "get", "/api/admin/stats/").data
        self.assertEqual(stats["totals"], {"all": 2, "completed": 1, "pending": 1})
        self.assertEqual(stats["by_status"]["officer_assigned"], 1)
        row = next(o for o in stats["officers"] if o["id"] == self.officer.id)
        self.assertEqual((row["completed_tasks"], row["active_tasks"], row["points"]), (1, 1, 3))
        self.assertEqual(row["current_tasks"][0]["id"], rid)

    def test_admin_only_endpoints(self):
        for url in ("/api/admin/stats/", "/api/admin/officers/", "/api/admin/audit-logs/"):
            self.assertEqual(self.call(self.citizen, "get", url).status_code, 403)
            self.assertEqual(self.call(self.officer, "get", url).status_code, 403)
            self.assertEqual(self.call(self.admin, "get", url).status_code, 200)

    def test_admin_creates_officer_and_manages_categories(self):
        res = self.call(self.admin, "post", "/api/admin/officers/",
                        {"email": "o3@t.com", "phone": "+8801733333333", "full_name": "O3", "password": "Str0ng!Pass99"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email="o3@t.com").role, "officer")
        self.assertEqual(self.call(self.citizen, "post", "/api/categories/", {"name": "Hack"}).status_code, 403)
        made = self.call(self.admin, "post", "/api/categories/", {"name": "Passport Request"})
        self.assertEqual(made.status_code, 201)
        self.call(self.admin, "patch", f"/api/categories/{made.data['id']}/", {"is_active": False})
        names = [c["name"] for c in self.call(self.citizen, "get", "/api/categories/").data]
        self.assertNotIn("Passport Request", names)
        self.assertIn("NID Request", names)


class AuditTests(BaseAPITest):
    def test_actions_are_logged(self):
        self.complete_flow("medium")
        logs = self.call(self.admin, "get", "/api/admin/audit-logs/?page_size=100").data["results"]
        actions = {l["action"] for l in logs}
        self.assertTrue({"request.created", "request.validated", "request.assigned", "request.status_changed"} <= actions)
        done = next(l for l in logs if l["action"] == "request.status_changed" and l["metadata"]["to"] == "task_done")
        self.assertEqual(done["metadata"]["points_awarded"], 2)
        self.assertEqual(done["actor_email"], self.officer.email)

    def test_login_success_and_failure_logged_and_filterable(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.post("/api/auth/login/", {"email": "cit@t.com", "password": "bad"}, format="json")
        c.post("/api/auth/login/", {"email": "cit@t.com", "password": "Str0ng!Pass99"}, format="json")
        logs = self.call(self.admin, "get", "/api/admin/audit-logs/?action=auth.login").data["results"]
        self.assertEqual({l["action"] for l in logs}, {"auth.login", "auth.login_failed"})
