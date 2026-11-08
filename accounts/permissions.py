from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_administrator(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "is_administrator", False))


class IsAdministrator(BasePermission):
    """Allows access only to users with the administrator role (or superusers)."""

    message = "Administrator permissions are required."

    def has_permission(self, request, view):
        return is_administrator(request.user)


class IsAdministratorOrReadOnly(BasePermission):
    """Anyone may read; only administrators may write."""

    message = "Administrator permissions are required to modify this resource."

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_administrator(request.user)
