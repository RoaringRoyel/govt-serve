from rest_framework import generics

from apps.service_requests.permissions import IsAdminRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = AuditLog.objects.all()
        action = self.request.query_params.get("action")
        actor = self.request.query_params.get("actor")
        if action:
            qs = qs.filter(action__startswith=action)
        if actor:
            qs = qs.filter(actor_email__icontains=actor)
        return qs
