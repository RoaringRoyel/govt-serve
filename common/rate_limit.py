"""Rate limiting behind a small interface (Dependency Inversion).

The limiter stores counters in Django's cache. In Docker the cache is Redis, whose
INCR is atomic, so the limit holds across all web replicas behind the load balancer.
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.core.cache import cache as default_cache


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, key: str, limit: int, window: int) -> RateLimitResult:
        """Register one attempt for `key` and say whether it is within `limit` per `window` seconds."""


class CacheWindowRateLimiter(RateLimiter):
    def __init__(self, cache=None):
        self._cache = cache or default_cache

    def hit(self, key, limit, window):
        now = int(time.time())
        bucket = now // window
        cache_key = f"ratelimit:{key}:{bucket}"
        self._cache.add(cache_key, 0, timeout=window + 1)  # no-op if it already exists
        try:
            count = self._cache.incr(cache_key)
        except ValueError:  # key expired between add() and incr()
            self._cache.set(cache_key, 1, timeout=window + 1)
            count = 1
        return RateLimitResult(
            allowed=count <= limit,
            remaining=max(limit - count, 0),
            retry_after=window - (now % window),
        )


_limiter = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = CacheWindowRateLimiter()
    return _limiter
