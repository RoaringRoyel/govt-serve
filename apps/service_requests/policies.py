from abc import ABC, abstractmethod

from django.conf import settings
from django.db.models import Count, Q

from apps.accounts.models import Role, User

from .models import ACTIVE_STATUSES, Priority, ServiceRequest, Status


class OfficerAvailabilityPolicy:
    """An officer is available while they hold fewer than N active tasks (OFFICER_MAX_ACTIVE_TASKS)."""

    def __init__(self, max_active=None):
        self._max_active = max_active

    @property
    def max_active(self):
        return self._max_active if self._max_active is not None else settings.OFFICER_MAX_ACTIVE_TASKS

    def available_officers(self):
        return (
            User.objects.filter(role=Role.OFFICER, is_active=True)
            .annotate(active_tasks=Count("assigned_requests", filter=Q(assigned_requests__status__in=ACTIVE_STATUSES)))
            .filter(active_tasks__lt=self.max_active)
            .order_by("full_name")
        )

    def is_available(self, officer):
        active = ServiceRequest.objects.filter(officer=officer, status__in=ACTIVE_STATUSES).count()
        return active < self.max_active


class PointsPolicy(ABC):
    @abstractmethod
    def points_for(self, priority: str) -> int: ...


class PriorityPointsPolicy(PointsPolicy):
    """High = 3, Medium = 2, Low = 1."""

    POINTS = {Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}

    def points_for(self, priority):
        return self.POINTS[Priority(priority)]


# Allowed status changes: current -> {next: roles allowed to perform it}
TRANSITIONS = {
    Status.NOT_VALIDATED: {Status.VALIDATED: {Role.ADMIN}},
    Status.VALIDATED: {Status.OFFICER_ASSIGNED: {Role.ADMIN}},
    Status.OFFICER_ASSIGNED: {Status.PENDING: {Role.OFFICER}},
    Status.PENDING: {Status.TASK_DONE: {Role.OFFICER}},
}
