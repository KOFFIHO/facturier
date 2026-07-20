from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import CashSession, Company, Product, Sale, SaleItem, SalePayment, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    list_display = ("phone_number", "full_name", "role", "company", "is_active")
    list_filter = ("role", "company")
    ordering = ("full_name",)
    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("Informations", {"fields": ("full_name", "role", "company")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {"fields": ("phone_number", "full_name", "role", "company", "password1", "password2")}),
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "tva_rate", "phone", "email")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "price", "stock", "critical_threshold")
    list_filter = ("company",)
    search_fields = ("name",)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "client_name", "total", "seller", "created_at")
    list_filter = ("company",)
    inlines = [SaleItemInline, SalePaymentInline]


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ("seller", "company", "opened_at", "planned_closed_at", "is_closed")
    list_filter = ("company", "is_closed")
