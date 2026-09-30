from django.conf import settings
from rest_framework.exceptions import Throttled
from rest_framework.throttling import BaseThrottle

from .rate_limit import get_rate_limiter
from .utils import client_ip


class _RedisBackedThrottle(BaseThrottle):
    scope = "api"

    def get_limit(self):
        raise NotImplementedError

    def get_key(self, request):
        raise NotImplementedError

    def allow_request(self, request, view):
        result = get_rate_limiter().hit(
            f"{self.scope}:{self.get_key(request)}", self.get_limit(), settings.RATE_LIMIT_WINDOW_SECONDS
        )
        self._retry_after = result.retry_after
        return result.allowed

    def wait(self):
        return getattr(self, "_retry_after", None)


class AuthRateThrottle(_RedisBackedThrottle):
    """Login / register: 50 attempts per minute per IP by default (brute force + DDoS guard)."""

    scope = "auth"

    def get_limit(self):
        return settings.RATE_LIMIT_AUTH_PER_MIN

    def get_key(self, request):
        return client_ip(request) or "unknown"


class GlobalRateThrottle(_RedisBackedThrottle):
    """All other endpoints: per authenticated user, or per IP for anonymous callers."""

    scope = "api"

    def get_limit(self):
        return settings.RATE_LIMIT_API_PER_MIN

    def get_key(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return f"user:{user.pk}"
        return f"ip:{client_ip(request) or 'unknown'}"
