from datetime import date
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from api.views import AuditLogMixin, CustomPagination
from users.permissions import ManagerWriteOrReadOnly, IsAdminOrReadOnly
from .models import Employee, Attendance, Leave, PayrollRun, Payslip
from .serializers import (
    EmployeeSerializer, AttendanceSerializer, LeaveSerializer,
    PayrollRunSerializer, PayslipSerializer,
)
from .services import run_payroll, recalculate_payslip


class EmployeeViewSet(AuditLogMixin, ModelViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "role_title", "phone_number", "email"]
    ordering = ["name"]


class AttendanceViewSet(AuditLogMixin, ModelViewSet):
    queryset = Attendance.objects.select_related("employee").all()
    serializer_class = AttendanceSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["employee", "date", "status"]

    @action(detail=False, methods=["post"], url_path="mark")
    def mark(self, request):
        """Upsert one attendance record for (employee, date)."""
        employee_id = request.data.get("employee")
        day = request.data.get("date")
        att_status = request.data.get("status", Attendance.PRESENT)
        if not employee_id or not day:
            return Response({"detail": "employee and date are required."},
                            status=status.HTTP_400_BAD_REQUEST)
        record, _ = Attendance.objects.update_or_create(
            employee_id=employee_id, date=day,
            defaults={"status": att_status, "note": request.data.get("note")},
        )
        return Response(AttendanceSerializer(record).data)


class LeaveViewSet(AuditLogMixin, ModelViewSet):
    queryset = Leave.objects.select_related("employee").all()
    serializer_class = LeaveSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["employee", "status", "leave_type"]

    def _set_status(self, request, pk, new_status):
        leave = self.get_object()
        leave.status = new_status
        leave.save(update_fields=["status"])
        return Response(LeaveSerializer(leave).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._set_status(request, pk, Leave.APPROVED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._set_status(request, pk, Leave.REJECTED)


class PayrollRunViewSet(AuditLogMixin, ModelViewSet):
    queryset = PayrollRun.objects.prefetch_related("payslips__employee").all()
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAdminOrReadOnly]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        """POST {month: 'YYYY-MM-01'} — compute payroll for that month."""
        month_raw = request.data.get("month")
        if not month_raw:
            return Response({"detail": "month is required (YYYY-MM-DD)."},
                            status=status.HTTP_400_BAD_REQUEST)
        month = date.fromisoformat(str(month_raw))
        run = run_payroll(month=month, user=request.user, notes=request.data.get("notes"))
        return Response(PayrollRunSerializer(run).data, status=status.HTTP_201_CREATED)


class PayslipViewSet(AuditLogMixin, ModelViewSet):
    queryset = Payslip.objects.select_related("employee", "run").all()
    serializer_class = PayslipSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["run", "employee", "is_paid"]
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        super().perform_update(serializer)  # saves + audit log
        recalculate_payslip(serializer.instance)
