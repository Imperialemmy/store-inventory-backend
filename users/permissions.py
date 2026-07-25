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


class AdminOnly(BasePermission):
    """Only active, authenticated administrators may use the endpoint."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and _role(request) == "admin"


class CustomerAccess(BasePermission):
    """Admins and sellers manage customer details; only admins delete them."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method == "DELETE":
            return _role(request) == "admin"
        return request.method in SAFE_METHODS or _role(request) in ("admin", "seller")


class SellerWriteOrReadOnly(BasePermission):
    """Authenticated users can read; admins and sellers can write
    (customers, sales)."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return _role(request) in ("admin", "seller")
