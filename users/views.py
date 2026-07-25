import uuid

from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission, AllowAny, IsAuthenticated

from .models import CustomUser
from .serializers import UserAdminSerializer


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, "role", None) == "admin"


class AccountStatusView(APIView):
    """Public: after a failed login, lets the UI tell a pending seller apart
    from a wrong password. Only reports the pending/awaiting-approval state;
    it never validates a password."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        user = CustomUser.objects.filter(username__iexact=username).first()
        pending = bool(user and not user.is_active and user.role == CustomUser.SELLER)
        return Response({"pending": pending})


class LogoutView(APIView):
    """Invalidate every JWT from the current session before signing out."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.session_id = uuid.uuid4()
        request.user.save(update_fields=["session_id"])
        return Response(status=status.HTTP_204_NO_CONTENT)


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
