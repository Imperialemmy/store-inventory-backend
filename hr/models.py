from decimal import Decimal
from django.db import models
from django.utils.timezone import now, localdate
from users.models import CustomUser


class Employee(models.Model):
    """A staff member. Optionally linked to a login account."""
    user = models.OneToOneField(
        CustomUser, related_name="employee_profile", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    name = models.CharField(max_length=150)
    role_title = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    start_date = models.DateField(default=localdate)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    performance_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Attendance(models.Model):
    PRESENT = "present"
    ABSENT = "absent"
    HALF_DAY = "half_day"
    ON_LEAVE = "on_leave"
    STATUS_CHOICES = (
        (PRESENT, "Present"),
        (ABSENT, "Absent"),
        (HALF_DAY, "Half day"),
        (ON_LEAVE, "On leave"),
    )

    employee = models.ForeignKey(Employee, related_name="attendance", on_delete=models.CASCADE)
    date = models.DateField(default=localdate)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PRESENT)
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ("employee", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.employee} — {self.date} ({self.status})"


class Leave(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    )
    ANNUAL = "annual"
    SICK = "sick"
    UNPAID = "unpaid"
    OTHER = "other"
    TYPE_CHOICES = (
        (ANNUAL, "Annual"),
        (SICK, "Sick"),
        (UNPAID, "Unpaid"),
        (OTHER, "Other"),
    )

    employee = models.ForeignKey(Employee, related_name="leaves", on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee} — {self.leave_type} {self.start_date}→{self.end_date}"


class PayrollRun(models.Model):
    """One payroll computation for a calendar month (stored as its 1st)."""
    month = models.DateField(unique=True, help_text="First day of the payroll month.")
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=now)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"Payroll {self.month:%B %Y}"

    @property
    def total_net(self):
        return self.payslips.aggregate(t=models.Sum("net_pay"))["t"] or Decimal("0")


class Payslip(models.Model):
    run = models.ForeignKey(PayrollRun, related_name="payslips", on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, related_name="payslips", on_delete=models.PROTECT)
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    working_days = models.PositiveIntegerField(default=0)
    days_absent = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    paid_on = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("run", "employee")
        ordering = ["employee__name"]

    def __str__(self):
        return f"{self.employee} — {self.run}"
