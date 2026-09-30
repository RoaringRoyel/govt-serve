from collections import defaultdict

from django.db.models import Count, Q

from apps.accounts.models import Role, User

from .models import ACTIVE_STATUSES, Category, Priority, ServiceRequest, Status
from .policies import OfficerAvailabilityPolicy


def officer_overview(policy=None):
    """One row per officer: what they are doing now, how many they finished, points, availability."""
    policy = policy or OfficerAvailabilityPolicy()
    officers = list(
        User.objects.filter(role=Role.OFFICER)
        .annotate(
            active_tasks=Count("assigned_requests", filter=Q(assigned_requests__status__in=ACTIVE_STATUSES)),
            completed_tasks=Count("assigned_requests", filter=Q(assigned_requests__status=Status.TASK_DONE)),
        )
        .order_by("full_name")
    )
    current = defaultdict(list)
    tasks = ServiceRequest.objects.filter(officer__in=officers, status__in=ACTIVE_STATUSES).select_related("category")
    for t in tasks:
        current[t.officer_id].append(
            {"id": t.id, "title": t.title, "category": t.category.name, "priority": t.priority, "status": t.status}
        )
    return [
        {
            "id": o.id,
            "full_name": o.full_name,
            "email": o.email,
            "phone": o.phone,
            "points": o.points,
            "active_tasks": o.active_tasks,
            "completed_tasks": o.completed_tasks,
            "available": o.is_active and o.active_tasks < policy.max_active,
            "current_tasks": current[o.id],
        }
        for o in officers
    ]


def system_overview():
    qs = ServiceRequest.objects
    by_status = {s: 0 for s in Status.values}
    by_status.update({row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))})
    by_priority = {p: 0 for p in Priority.values}
    by_priority.update({row["priority"]: row["n"] for row in qs.values("priority").annotate(n=Count("id"))})
    by_category = [
        {"category": c.name, "count": c.n}
        for c in Category.objects.annotate(n=Count("requests")).order_by("-n", "name")
    ]
    total = sum(by_status.values())
    done = by_status[Status.TASK_DONE]
    return {
        "totals": {"all": total, "completed": done, "pending": total - done},
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": by_category,
        "officers": officer_overview(),
    }
