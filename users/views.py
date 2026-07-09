from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission

from .models import CustomUser
from .serializers import UserAdminSerializer


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", None) == "admin"


class UserAdminViewSet(ReadOnlyModelViewSet):
    """Admin team management: list users and approve / deactivate sellers."""
    queryset = CustomUser.objects.all().order_by("-date_joined")
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdmin]

    def _guard_self(self, user, request):
        if user.id == request.user.id:
            return Response({"detail": "You cannot change your own account here."},
                            status=status.HTTP_400_BAD_REQUEST)
        return None

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(UserAdminSerializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        blocked = self._guard_self(user, request)
        if blocked:
            return blocked
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(UserAdminSerializer(user).data)

    @action(detail=True, methods=["post"])
    def remove(self, request, pk=None):
        user = self.get_object()
        blocked = self._guard_self(user, request)
        if blocked:
            return blocked
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
