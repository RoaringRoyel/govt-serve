from apps.accounts.models import Role

from .models import CommentAudience, ServiceRequest


def requests_visible_to(user):
    qs = ServiceRequest.objects.select_related("citizen", "category", "officer")
    if user.role == Role.ADMIN:
        return qs
    if user.role == Role.OFFICER:
        return qs.filter(officer=user)
    return qs.filter(citizen=user)


def comments_visible_to(user, service_request):
    qs = service_request.comments.select_related("author")
    if user.role == Role.CITIZEN:
        qs = qs.filter(audience=CommentAudience.CITIZEN)
    return qs
