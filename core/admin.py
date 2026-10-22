from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Approvisionnement, CashSession, Commande, CommandeAvance, CommandeItem, CommandeLivraison,
    Company, Depense, Employee, Product, Sale, SaleItem, SalePayment, Service, SyncState, User,
)


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


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "default_price", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "role", "company", "phone", "is_active")
    list_filter = ("company", "role", "is_active")
    search_fields = ("full_name", "phone")


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ("date", "type_depense", "label", "amount", "commande", "company")
    list_filter = ("company", "type_depense")
    search_fields = ("label", "type_depense")
    date_hierarchy = "date"


@admin.register(Approvisionnement)
class ApprovisionnementAdmin(admin.ModelAdmin):
    list_display = ("date", "product", "quantity", "unit_cost", "company")
    list_filter = ("company",)
    date_hierarchy = "date"


class CommandeItemInline(admin.TabularInline):
    model = CommandeItem
    extra = 0


class CommandeAvanceInline(admin.TabularInline):
    model = CommandeAvance
    extra = 0


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ("order_code", "client_name", "client_phone", "company", "expected_delivery_date", "created_at")
    list_filter = ("company",)
    search_fields = ("client_name", "client_phone")
    inlines = [CommandeItemInline, CommandeAvanceInline]


@admin.register(CommandeLivraison)
class CommandeLivraisonAdmin(admin.ModelAdmin):
    list_display = ("commande_item", "quantity", "date")
    date_hierarchy = "date"


@admin.register(SyncState)
class SyncStateAdmin(admin.ModelAdmin):
    list_display = ("key", "last_synced_at")
