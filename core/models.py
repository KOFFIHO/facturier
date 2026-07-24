# Modèles de données du Facturier Automatique (Côte d'Ivoire - F CFA).
# Architecture multi-entreprises : Company (une par entreprise gérée par
# l'Admin), User (ADMIN global ou SELLER rattaché à une Company), Product
# et Sale rattachés chacun à une Company précise.

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

# Validateur réutilisable pour garantir exactement 10 chiffres (Format CI)
phone_validator = RegexValidator(
    regex=r'^\d{10}$',
    message="Le numéro de téléphone doit contenir exactement 10 chiffres."
)


class Company(models.Model):
    """Une entreprise gérée sur la plateforme (identité, logo, cachet, TVA)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(
        max_length=10, 
        validators=[phone_validator], 
        null=True, 
        blank=True
    )
    email = models.EmailField(null=True, blank=True)
    website = models.CharField(max_length=200, null=True, blank=True)
    tva_rate = models.FloatField(default=18)  # Taux de TVA en Côte d'Ivoire : 18% par défaut
    logo = models.ImageField(upload_to="", null=True, blank=True)
    stamp = models.ImageField(upload_to="", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    """Manager personnalisé : l'identifiant de connexion est le numéro de téléphone."""

    def create_user(self, phone_number, full_name, password=None, role="SELLER", company=None):
        if not phone_number:
            raise ValueError("Le numéro de téléphone est requis.")
        user = self.model(phone_number=phone_number, full_name=full_name, role=role, company=company)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, full_name, password=None):
        user = self.create_user(phone_number, full_name, password, role=User.Role.ADMIN)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """Utilisateur de la plateforme : Administrateur (global) ou Vendeur
    (rattaché à une seule entreprise)."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        SELLER = "SELLER", "Vendeur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=10, 
        unique=True, 
        validators=[phone_validator]
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.SELLER)
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"


class Product(models.Model):
    """Produit du catalogue / stock, rattaché à une entreprise précise."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    price = models.FloatField()  # Prix unitaire en F CFA
    stock = models.IntegerField(default=0)
    critical_threshold = models.IntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentMethod(models.TextChoices):
    ESPECES = "ESPECES", "Espèces"
    ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"
    MTN_MONEY = "MTN_MONEY", "MTN Money"
    MOOV_MONEY = "MOOV_MONEY", "Moov Money"
    CARTE = "CARTE", "Carte bancaire"
    CHEQUE = "CHEQUE", "Chèque"
    AUTRE = "AUTRE", "Autre"


class DiscountType(models.TextChoices):
    NONE = "NONE", "Aucune réduction"
    PERCENTAGE = "PERCENTAGE", "Pourcentage"
    AMOUNT = "AMOUNT", "Montant fixe"


class Sale(models.Model):
    """Vente / facture générée depuis la Caisse. `id` sert de numéro de facture."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="sales")
    client_name = models.CharField(max_length=200, null=True, blank=True)
    client_phone = models.CharField(
        max_length=10, 
        validators=[phone_validator], 
        null=True, 
        blank=True
    )
    notes = models.TextField(null=True, blank=True)

    discount_type = models.CharField(max_length=12, choices=DiscountType.choices, default=DiscountType.NONE)
    discount_value = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)

    sub_total = models.FloatField()
    tva_amount = models.FloatField()
    total = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    seller = models.ForeignKey(User, related_name="sales", on_delete=models.PROTECT)

    class Meta:
        db_table = "sales"
        ordering = ["-created_at"]

    @property
    def invoice_number(self):
        return self.id

    def __str__(self):
        return f"Facture #{self.id}"


class SalePayment(models.Model):
    """Ligne de règlement d'une vente (permet de combiner plusieurs modes de paiement)."""

    sale = models.ForeignKey(Sale, related_name="payments", on_delete=models.CASCADE)
    method = models.CharField(max_length=15, choices=PaymentMethod.choices)
    amount = models.FloatField()

    class Meta:
        db_table = "sale_payments"


class CashSession(models.Model):
    """Session de caisse d'un vendeur : heure d'ouverture + heure de
    fermeture prévue (prolongeable), avec fermeture automatique à échéance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="cash_sessions")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cash_sessions")
    opened_at = models.DateTimeField()
    planned_closed_at = models.DateTimeField()
    actual_closed_at = models.DateTimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cash_sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session de {self.seller.full_name} ({self.opened_at:%d/%m/%Y %H:%M})"


class SaleItem(models.Model):
    """Ligne d'une vente. `is_gift` : produit offert (0 F CFA dans les totaux).
    `discount_amount` : remise en F CFA appliquée sur cette ligne uniquement
    (en plus de l'éventuelle réduction globale de la vente)."""

    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="sale_items", on_delete=models.PROTECT)
    quantity = models.IntegerField()
    price = models.FloatField()
    is_gift = models.BooleanField(default=False)
    discount_amount = models.FloatField(default=0)

    class Meta:
        db_table = "sale_items"