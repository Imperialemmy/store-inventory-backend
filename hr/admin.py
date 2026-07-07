from django.contrib import admin
from .models import Employee, Attendance, Leave, PayrollRun, Payslip


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "role_title", "phone_number", "monthly_salary", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "role_title")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "date", "status")
    list_filter = ("status", "date")


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ("employee", "leave_type", "start_date", "end_date", "status")
    list_filter = ("status", "leave_type")


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("month", "created_by", "created_at")
    inlines = [PayslipInline]


admin.site.register(Payslip)
