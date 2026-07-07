from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from .models import Employee, Attendance
from .services import working_days_in_month, run_payroll


class PayrollTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="hradmin", email="h@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)
        self.employee = Employee.objects.create(
            name="Chika Obi", monthly_salary=Decimal("150000"),
            start_date=date(2026, 1, 5))

    def test_working_days_june_2026(self):
        # June 2026 has 22 weekdays.
        self.assertEqual(working_days_in_month(date(2026, 6, 1)), 22)

    def test_payroll_deducts_absences(self):
        Attendance.objects.create(employee=self.employee, date=date(2026, 6, 2), status="absent")
        Attendance.objects.create(employee=self.employee, date=date(2026, 6, 3), status="absent")
        Attendance.objects.create(employee=self.employee, date=date(2026, 6, 4), status="half_day")
        run = run_payroll(month=date(2026, 6, 1), user=self.admin)
        slip = run.payslips.get(employee=self.employee)
        self.assertEqual(slip.days_absent, Decimal("2.5"))
        # 150000 / 22 = 6818.18/day; ×2.5 = 17045.45
        self.assertEqual(slip.absence_deduction, Decimal("17045.45"))
        self.assertEqual(slip.net_pay, Decimal("132954.55"))

    def test_on_leave_days_are_paid(self):
        Attendance.objects.create(employee=self.employee, date=date(2026, 6, 2), status="on_leave")
        run = run_payroll(month=date(2026, 6, 1))
        slip = run.payslips.get(employee=self.employee)
        self.assertEqual(slip.net_pay, Decimal("150000.00"))

    def test_duplicate_month_blocked(self):
        self.client_api.post("/api/v1/payroll-runs/", {"month": "2026-06-01"}, format="json")
        res = self.client_api.post("/api/v1/payroll-runs/", {"month": "2026-06-15"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_payslip_bonus_recalculates_net(self):
        run_data = self.client_api.post(
            "/api/v1/payroll-runs/", {"month": "2026-06-01"}, format="json").json()
        slip_id = run_data["payslips"][0]["id"]
        self.client_api.patch(f"/api/v1/payslips/{slip_id}/", {
            "bonus": "10000", "other_deduction": "2000"}, format="json")
        slip = self.client_api.get(f"/api/v1/payslips/{slip_id}/").json()
        self.assertEqual(slip["net_pay"], "158000.00")

    def test_attendance_mark_upserts(self):
        for status in ("present", "absent"):
            res = self.client_api.post("/api/v1/attendance/mark/", {
                "employee": self.employee.id, "date": "2026-06-09", "status": status,
            }, format="json")
            self.assertEqual(res.status_code, 200)
        self.assertEqual(Attendance.objects.filter(
            employee=self.employee, date=date(2026, 6, 9)).count(), 1)
        self.assertEqual(Attendance.objects.get(
            employee=self.employee, date=date(2026, 6, 9)).status, "absent")

    def test_leave_approval_flow(self):
        leave = self.client_api.post("/api/v1/leaves/", {
            "employee": self.employee.id, "leave_type": "annual",
            "start_date": "2026-06-10", "end_date": "2026-06-12",
        }, format="json").json()
        self.assertEqual(leave["status"], "pending")
        approved = self.client_api.post(f"/api/v1/leaves/{leave['id']}/approve/").json()
        self.assertEqual(approved["status"], "approved")
