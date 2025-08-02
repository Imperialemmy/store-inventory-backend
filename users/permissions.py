from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminOrReadOnly(BasePermission):
    """
    - Allow all authenticated users to view (GET, HEAD, OPTIONS).
    - Only admins can create, update, or delete.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return request.user.is_authenticated  # or True if you want anonymous users to view
        return request.user.is_authenticated and request.user.role == 'admin'
