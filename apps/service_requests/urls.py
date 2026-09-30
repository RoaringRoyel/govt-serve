from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .admin_views import AvailableOfficersView, OfficerListCreateView, StatsView
from .views import CategoryViewSet, ServiceRequestViewSet

router = DefaultRouter()
router.register("requests", ServiceRequestViewSet, basename="request")
router.register("categories", CategoryViewSet, basename="category")


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health),
    path("admin/officers/", OfficerListCreateView.as_view(), name="officers"),
    path("admin/officers/available/", AvailableOfficersView.as_view(), name="officers-available"),
    path("admin/stats/", StatsView.as_view(), name="stats"),
    path("", include(router.urls)),
]
