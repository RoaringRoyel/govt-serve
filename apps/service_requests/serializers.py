from rest_framework import serializers


from .models import Attachment, Category, Comment, CommentAudience, ServiceRequest, Status


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "description", "is_active")


class ServiceRequestSerializer(serializers.ModelSerializer):
    citizen_name = serializers.CharField(source="citizen.full_name", read_only=True)
    citizen_email = serializers.CharField(source="citizen.email", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    officer_name = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = (
            "id", "category", "category_name", "title", "description", "remarks", "priority", "priority_label",
            "status", "status_label", "citizen", "citizen_name", "citizen_email", "officer", "officer_name",
            "points_awarded", "created_at", "updated_at", "completed_at",
        )
        read_only_fields = ("status", "citizen", "officer", "points_awarded", "created_at", "updated_at", "completed_at")

    def get_officer_name(self, obj):
        return obj.officer.full_name if obj.officer_id else None

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("This category is not available.")
        return value


class AssignSerializer(serializers.Serializer):
    officer_id = serializers.IntegerField()


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[Status.PENDING, Status.TASK_DONE])


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    author_role = serializers.CharField(source="author.role", read_only=True)

    class Meta:
        model = Comment
        fields = ("id", "author_name", "author_role", "body", "audience", "created_at")
        read_only_fields = fields


class CommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000)
    audience = serializers.ChoiceField(choices=CommentAudience.choices, default=CommentAudience.CITIZEN)


class AttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)

    class Meta:
        model = Attachment
        fields = ("id", "original_name", "size", "uploaded_by_name", "download_url", "created_at")
        read_only_fields = fields

    def get_download_url(self, obj):
        return f"/api/requests/{obj.request_id}/attachments/{obj.pk}/download/"


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
