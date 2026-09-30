from django.conf import settings


def client_ip(request):
    """Client IP. X-Forwarded-For is honoured only when running behind our own proxy."""
    if request is None:
        return None
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
