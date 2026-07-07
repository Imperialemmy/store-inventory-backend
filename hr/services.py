import calendar
from datetime import date
from decimal import Decimal
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Employee, Attendance, PayrollRun, Payslip

TWO_DP = Decimal("0.01")


def working_days_in_month(month: date) -> int:
    """Count weekdays (Mon–Fri) in the month containing `month`."""
    _, days = calendar.monthrange(month.year, month.month)
    return sum(
        1 for d in range(1, days + 1)
        if date(month.year, month.month, d).weekday() < 5
    )


def absence_days(employee: Employee, month: date) -> Decimal:
    """Days to deduct for the month.

    Only explicit attendance records count against pay: 'absent' is a full
    day, 'half_day' is half. Days with no record, 'present', or 'on_leave'
    (approved leave is paid) cost nothing.
    """
    _, days = calendar.monthrange(month.year, month.month)
    records = Attendance.objects.filter(
        employee=employee,
        date__gte=date(month.year, month.month, 1),
        date__lte=date(month.year, month.month, days),
    )
    total = Decimal("0")
    for rec in records:
        if rec.status == Attendance.ABSENT:
            total += Decimal("1")
        elif rec.status == Attendance.HALF_DAY:
            total += Decimal("0.5")
    return total


@transaction.atomic
def run_payroll(*, month: date, user=None, notes=None) -> PayrollRun:
    """Generate a payroll run with one payslip per active employee.

    net = base − (base / working_days) × absent_days.
    Manual deductions/bonuses can be edited on each payslip afterwards.
    """
    month = month.replace(day=1)
    if PayrollRun.objects.filter(month=month).exists():
        raise ValidationError(f"Payroll for {month:%B %Y} has already been run.")

    employees = Employee.objects.filter(is_active=True)
    if not employees.exists():
        raise ValidationError("No active employees to run payroll for.")

    run = PayrollRun.objects.create(month=month, created_by=user, notes=notes)
    days = working_days_in_month(month)

    for employee in employees:
        absent = absence_days(employee, month)
        base = employee.monthly_salary or Decimal("0")
        per_day = (base / days).quantize(TWO_DP) if days else Decimal("0")
        deduction = (per_day * absent).quantize(TWO_DP)
        net = (base - deduction).quantize(TWO_DP)
        Payslip.objects.create(
            run=run,
            employee=employee,
            base_salary=base,
            working_days=days,
            days_absent=absent,
            absence_deduction=deduction,
            net_pay=net,
        )
    return run


def recalculate_payslip(payslip: Payslip) -> Payslip:
    """Recompute net pay after manual deduction/bonus edits."""
    payslip.net_pay = (
        payslip.base_salary
        - payslip.absence_deduction
        - payslip.other_deduction
        + payslip.bonus
    ).quantize(TWO_DP)
    payslip.save(update_fields=["net_pay"])
    return payslip
