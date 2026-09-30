from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ("id", "created_at", "actor", "actor_email", "action", "target_type", "target_id", "metadata", "ip_address")
        read_only_fields = fields
