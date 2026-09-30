import logging

from common.utils import client_ip

from .models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Single place that writes audit entries. Other modules depend on `log()` only."""

    def log(self, action, actor=None, target=None, metadata=None, request=None):
        actor = actor if getattr(actor, "is_authenticated", False) else None
        if actor is None and request is not None:
            user = getattr(request, "user", None)
            actor = user if getattr(user, "is_authenticated", False) else None
        try:
            return AuditLog.objects.create(
                actor=actor,
                actor_email=(actor.email if actor else (metadata or {}).get("email", "")),
                action=action,
                target_type=target.__class__.__name__ if target is not None else "",
                target_id=str(target.pk) if target is not None else "",
                metadata=metadata or {},
                ip_address=client_ip(request),
            )
        except Exception:  # auditing must never break the business action
            logger.exception("Failed to write audit log for %s", action)


audit = AuditService()
