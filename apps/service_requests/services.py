import os

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role, User
from apps.audit.services import audit
from common.exceptions import BusinessRuleViolation, InvalidTransition

from .models import Attachment, Comment, CommentAudience, ServiceRequest, Status
from .policies import TRANSITIONS, OfficerAvailabilityPolicy, PointsPolicy, PriorityPointsPolicy


class RequestService:
    """Use-cases for service requests. Rules live in injected policies, HTTP concerns live in views."""

    def __init__(self, availability: OfficerAvailabilityPolicy = None, points: PointsPolicy = None, audit_service=None):
        self.availability = availability or OfficerAvailabilityPolicy()
        self.points = points or PriorityPointsPolicy()
        self.audit = audit_service or audit

    # ---- helpers ----
    @staticmethod
    def _lock(req):
        # of=("self",): lock only the request row. PostgreSQL refuses FOR UPDATE across the nullable
        # side of the LEFT JOIN that select_related("officer") creates.
        return (
            ServiceRequest.objects.select_for_update(of=("self",))
            .select_related("citizen", "category", "officer")
            .get(pk=req.pk)
        )

    @staticmethod
    def _ensure_transition(req, actor, new_status):
        allowed = TRANSITIONS.get(req.status, {})
        if new_status not in allowed:
            raise InvalidTransition(f"Cannot move a request from '{req.status}' to '{new_status}'.")
        if actor.role not in allowed[new_status]:
            raise PermissionDenied("Your role cannot perform this status change.")

    # ---- citizen ----
    @transaction.atomic
    def create(self, citizen, **data):
        req = ServiceRequest.objects.create(citizen=citizen, **data)
        self.audit.log("request.created", actor=citizen, target=req, metadata={"priority": req.priority})
        return req

    @transaction.atomic
    def update(self, req, actor, **data):
        req = self._lock(req)
        if actor.role != Role.CITIZEN or req.citizen_id != actor.id:
            raise PermissionDenied("Only the owner can edit a request.")
        if req.status != Status.NOT_VALIDATED:
            raise BusinessRuleViolation("A request can only be edited before it is validated.")
        for field, value in data.items():
            setattr(req, field, value)
        req.save()
        self.audit.log("request.updated", actor=actor, target=req, metadata={"fields": sorted(data)})
        return req

    # ---- admin ----
    @transaction.atomic
    def validate(self, req, admin):
        req = self._lock(req)
        self._ensure_transition(req, admin, Status.VALIDATED)
        req.status = Status.VALIDATED
        req.save()
        self.audit.log("request.validated", actor=admin, target=req)
        return req

    @transaction.atomic
    def assign(self, req, admin, officer_id):
        req = self._lock(req)
        if admin.role != Role.ADMIN:
            raise PermissionDenied("Only admins can assign officers.")
        if req.status not in (Status.VALIDATED, Status.OFFICER_ASSIGNED):
            raise InvalidTransition("Only validated requests (not yet started) can be assigned.")
        officer = User.objects.select_for_update().filter(pk=officer_id, role=Role.OFFICER, is_active=True).first()
        if officer is None:
            raise ValidationError({"officer_id": "No active officer with this id."})
        if req.officer_id != officer.id and not self.availability.is_available(officer):
            raise BusinessRuleViolation("This officer is not available right now.")
        previous = req.officer_id
        req.officer = officer
        req.status = Status.OFFICER_ASSIGNED
        req.save()
        self.audit.log(
            "request.assigned", actor=admin, target=req, metadata={"officer_id": officer.id, "previous_officer_id": previous}
        )
        return req

    # ---- officer ----
    @transaction.atomic
    def change_status(self, req, actor, new_status):
        req = self._lock(req)
        if actor.role == Role.OFFICER and req.officer_id != actor.id:
            raise PermissionDenied("This request is not assigned to you.")
        old = req.status
        self._ensure_transition(req, actor, new_status)
        req.status = new_status
        if new_status == Status.TASK_DONE:
            earned = self.points.points_for(req.priority)
            req.completed_at = timezone.now()
            req.points_awarded = earned
            User.objects.filter(pk=req.officer_id).update(points=F("points") + earned)
        req.save()
        self.audit.log(
            "request.status_changed",
            actor=actor,
            target=req,
            metadata={"from": old, "to": new_status, "points_awarded": req.points_awarded},
        )
        return req

    # ---- comments & files ----
    @transaction.atomic
    def add_comment(self, req, author, body, audience=CommentAudience.CITIZEN):
        if author.role == Role.CITIZEN and audience != CommentAudience.CITIZEN:
            raise PermissionDenied("Citizens can only write comments visible to citizens.")
        comment = Comment.objects.create(request=req, author=author, body=body, audience=audience)
        self.audit.log("comment.added", actor=author, target=req, metadata={"audience": audience})
        return comment

    @transaction.atomic
    def add_attachment(self, req, user, upload):
        extension = os.path.splitext(upload.name)[1].lower()
        if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise ValidationError({"file": f"File type '{extension}' is not allowed."})
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise ValidationError({"file": f"File is larger than {settings.MAX_UPLOAD_MB} MB."})
        attachment = Attachment.objects.create(
            request=req, uploaded_by=user, file=upload, original_name=os.path.basename(upload.name)[:255], size=upload.size
        )
        self.audit.log("attachment.uploaded", actor=user, target=req, metadata={"name": attachment.original_name})
        return attachment


request_service = RequestService()