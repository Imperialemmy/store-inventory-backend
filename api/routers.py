from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BrandViewSet, CategoryViewSet, SizeViewSet, WareViewSet, WareVariantViewSet,
    BatchViewSet, ImageViewSet, UserViewSet,
    SupplierViewSet, WarehouseViewSet, AuditLogViewSet,
    CustomerViewSet, CustomerTagViewSet, NotificationsView,
)
from sales.views import SaleViewSet, PaymentViewSet, CreditNoteViewSet
from expenses.views import ExpenseViewSet, ExpenseCategoryViewSet
from hr.views import (
    EmployeeViewSet, AttendanceViewSet, LeaveViewSet,
    PayrollRunViewSet, PayslipViewSet,
)

router = DefaultRouter()
router.register(r'brands', BrandViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'sizes', SizeViewSet)
router.register(r'wares', WareViewSet)
router.register(r'variants', WareVariantViewSet)
router.register(r'batches', BatchViewSet)
router.register(r'images', ImageViewSet)
router.register(r'users', UserViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'warehouses', WarehouseViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'customer-tags', CustomerTagViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'credit-notes', CreditNoteViewSet)
router.register(r'expense-categories', ExpenseCategoryViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'attendance', AttendanceViewSet)
router.register(r'leaves', LeaveViewSet)
router.register(r'payroll-runs', PayrollRunViewSet)
router.register(r'payslips', PayslipViewSet)
router.register(r'audit-logs', AuditLogViewSet)

urlpatterns = [
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('', include(router.urls)),
]
