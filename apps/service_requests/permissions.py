from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role


class HasRole(BasePermission):
    allowed_roles: tuple = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.allowed_roles)


class IsCitizenRole(HasRole):
    allowed_roles = (Role.CITIZEN,)


class IsOfficerRole(HasRole):
    allowed_roles = (Role.OFFICER,)


class IsAdminRole(HasRole):
    allowed_roles = (Role.ADMIN,)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or user.role == Role.ADMIN
