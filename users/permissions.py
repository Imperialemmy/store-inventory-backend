from rest_framework.permissions import BasePermission, SAFE_METHODS


def _role(request):
    return getattr(request.user, "role", None)


class AdminWriteOrReadOnly(BasePermission):
    """Authenticated users can read; only admins can write (e.g. products)."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return _role(request) == "admin"


class SellerWriteOrReadOnly(BasePermission):
    """Authenticated users can read; admins and sellers can write
    (customers, sales)."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return _role(request) in ("admin", "seller")
