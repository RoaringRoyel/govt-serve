from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import OfficerCreateSerializer, UserSerializer
from apps.audit.services import audit

from .permissions import IsAdminRole
from .policies import OfficerAvailabilityPolicy
from .stats import officer_overview, system_overview


class OfficerListCreateView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        """Every officer with current tasks, completed count, points and availability."""
        return Response(officer_overview())

    @extend_schema(request=OfficerCreateSerializer, responses=UserSerializer)
    def post(self, request):
        serializer = OfficerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        officer = serializer.save()
        audit.log("officer.created", actor=request.user, target=officer, request=request)
        return Response(UserSerializer(officer).data, status=http.HTTP_201_CREATED)


class AvailableOfficersView(APIView):
    """Feeds the 'assign officer' dropdown: only officers who can take another task right now."""

    permission_classes = [IsAdminRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        officers = OfficerAvailabilityPolicy().available_officers()
        return Response(
            [{"id": o.id, "full_name": o.full_name, "active_tasks": o.active_tasks, "points": o.points} for o in officers]
        )


class StatsView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(system_overview())
