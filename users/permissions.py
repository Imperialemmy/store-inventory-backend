from rest_framework.permissions import BasePermission, SAFE_METHODS


def _role(request):
    return getattr(request.user, "role", None)


class IsAdminOrReadOnly(BasePermission):
    """
    - Allow all authenticated users to view (GET, HEAD, OPTIONS).
    - Only admins can create, update, or delete.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated
        return request.user.is_authenticated and _role(request) == 'admin'


class RoleWriteOrReadOnly(BasePermission):
    """Authenticated users can read; only the listed roles can write.

    Subclass with `write_roles = (...)`. Admin is always allowed to write.
    """
    write_roles: tuple = ()

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        role = _role(request)
        return role == "admin" or role in self.write_roles


class ManagerWriteOrReadOnly(RoleWriteOrReadOnly):
    """Admins and managers can write; everyone authenticated can read."""
    write_roles = ("manager",)


class WarehouseWriteOrReadOnly(RoleWriteOrReadOnly):
    """Admins, managers and warehouse staff can write (stock operations)."""
    write_roles = ("manager", "warehouse")


class SalesWriteOrReadOnly(RoleWriteOrReadOnly):
    """Admins, managers and sales staff can write (customers, sales)."""
    write_roles = ("manager", "sales")
