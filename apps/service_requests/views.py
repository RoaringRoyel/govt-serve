from django.shortcuts import get_object_or_404
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.services import audit

from .models import Category, ServiceRequest
from .permissions import IsAdminOrReadOnly, IsAdminRole, IsCitizenRole, IsOfficerRole
from .selectors import comments_visible_to, requests_visible_to
from .serializers import (
    AssignSerializer, AttachmentSerializer, AttachmentUploadSerializer, CategorySerializer, CommentCreateSerializer,
    CommentSerializer, ServiceRequestSerializer, StatusChangeSerializer,
)
from .services import request_service


class CategoryViewSet(viewsets.ModelViewSet):
    """Everyone can read active categories; only admins can create/rename/deactivate."""

    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Category.objects.none()
        qs = Category.objects.all()
        return qs if self.request.user.role == Role.ADMIN else qs.filter(is_active=True)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit.log("category.created", actor=self.request.user, target=obj, request=self.request)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit.log("category.updated", actor=self.request.user, target=obj, request=self.request)


class ServiceRequestViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceRequestSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    permission_map = {
        "create": [IsCitizenRole],
        "update": [IsCitizenRole],
        "partial_update": [IsCitizenRole],
        "validate": [IsAdminRole],
        "assign": [IsAdminRole],
        "set_status": [IsOfficerRole],
    }

    def get_permissions(self):
        return [cls() for cls in self.permission_map.get(self.action, [IsAuthenticated])]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ServiceRequest.objects.none()
        qs = requests_visible_to(self.request.user)
        p = self.request.query_params
        for param in ("status", "priority", "category", "officer"):
            if p.get(param):
                qs = qs.filter(**{f"{param}": p[param]})
        if p.get("q"):
            qs = qs.filter(title__icontains=p["q"])
        return qs

    # -- create / update go through the service layer so rules + audit are never bypassed --
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = request_service.create(request.user, **serializer.validated_data)
        return Response(self.get_serializer(obj).data, status=http.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        obj = request_service.update(instance, request.user, **serializer.validated_data)
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=None, responses=ServiceRequestSerializer)
    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        obj = request_service.validate(self.get_object(), request.user)
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=AssignSerializer, responses=ServiceRequestSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = request_service.assign(self.get_object(), request.user, serializer.validated_data["officer_id"])
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=StatusChangeSerializer, responses=ServiceRequestSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = request_service.change_status(self.get_object(), request.user, serializer.validated_data["status"])
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=CommentCreateSerializer, responses=CommentSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        obj = self.get_object()
        if request.method == "POST":
            serializer = CommentCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            comment = request_service.add_comment(obj, request.user, **serializer.validated_data)
            return Response(CommentSerializer(comment).data, status=http.HTTP_201_CREATED)
        return Response(CommentSerializer(comments_visible_to(request.user, obj), many=True).data)

    @extend_schema(request={"multipart/form-data": AttachmentUploadSerializer}, responses=AttachmentSerializer(many=True))
    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def attachments(self, request, pk=None):
        obj = self.get_object()
        if request.method == "POST":
            serializer = AttachmentUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            attachment = request_service.add_attachment(obj, request.user, serializer.validated_data["file"])
            return Response(AttachmentSerializer(attachment).data, status=http.HTTP_201_CREATED)
        return Response(AttachmentSerializer(obj.attachments.select_related("uploaded_by"), many=True).data)

    @extend_schema(responses={200: bytes})
    @action(detail=True, methods=["get"], url_path=r"attachments/(?P<attachment_id>\d+)/download")
    def download(self, request, pk=None, attachment_id=None):
        obj = self.get_object()  # scoped queryset => users can only download files of requests they may see
        attachment = get_object_or_404(obj.attachments, pk=attachment_id)
        return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_name)
