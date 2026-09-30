import os
import uuid

from django.conf import settings
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Priority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class Status(models.TextChoices):
    NOT_VALIDATED = "not_validated", "Not validated yet"
    VALIDATED = "validated", "Validated"
    OFFICER_ASSIGNED = "officer_assigned", "Officer assigned"
    PENDING = "pending", "Pending"
    TASK_DONE = "task_done", "Task done"


# An officer "has a task on their plate" while the request is in one of these states.
ACTIVE_STATUSES = (Status.OFFICER_ASSIGNED, Status.PENDING)


class ServiceRequest(models.Model):
    citizen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="requests")
    title = models.CharField(max_length=200)
    description = models.TextField()
    remarks = models.TextField(blank=True, help_text="Extra note from the citizen")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_VALIDATED)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_requests"
    )
    points_awarded = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "priority"])]

    def __str__(self):
        return f"#{self.pk} {self.title}"


class CommentAudience(models.TextChoices):
    CITIZEN = "citizen", "Visible to citizen"
    OFFICER = "officer", "Officer/admin only"


class Comment(models.Model):
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=CommentAudience.choices, default=CommentAudience.CITIZEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


def attachment_path(instance, filename):
    return f"attachments/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()}"


class Attachment(models.Model):
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
