from rest_framework import serializers
from .models import Employee, Attendance, Leave, PayrollRun, Payslip


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            "id", "user", "name", "role_title", "phone_number", "email",
            "start_date", "monthly_salary", "is_active", "performance_notes",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "employee", "employee_name", "date", "status", "note"]


class LeaveSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)

    class Meta:
        model = Leave
        fields = [
            "id", "employee", "employee_name", "leave_type", "start_date",
            "end_date", "reason", "status", "created_at",
        ]
        read_only_fields = ["status", "created_at"]

    def validate(self, data):
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError("End date cannot be before start date.")
        return data


class PayslipSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    month = serializers.DateField(source="run.month", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id", "run", "month", "employee", "employee_name", "base_salary",
            "working_days", "days_absent", "absence_deduction",
            "other_deduction", "bonus", "net_pay", "is_paid", "paid_on",
        ]
        read_only_fields = [
            "run", "employee", "base_salary", "working_days", "days_absent",
            "absence_deduction", "net_pay",
        ]


class PayrollRunSerializer(serializers.ModelSerializer):
    payslips = PayslipSerializer(many=True, read_only=True)
    total_net = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = PayrollRun
        fields = ["id", "month", "notes", "created_by_name", "total_net", "payslips", "created_at"]
        read_only_fields = ["created_at"]
