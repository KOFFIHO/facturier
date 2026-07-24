# Formulaires Django (validation + rendu des champs HTML).

from django import forms
from django.core.validators import RegexValidator

from .models import CashSession, Company, DiscountType, PaymentMethod, Product, User

_phone_validator = RegexValidator(
    regex=r"^\d{10}$",
    message="Le numéro de téléphone doit contenir exactement 10 chiffres.",
)


def phone_number_field(label="Numéro de téléphone"):
    """Champ téléphone standardisé : uniquement des chiffres, exactement 10,
    clavier numérique sur mobile (inputmode="numeric")."""
    return forms.CharField(
        label=label,
        validators=[_phone_validator],
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "pattern": "[0-9]{10}",
            "maxlength": "10",
            "placeholder": "0700000000",
        }),
    )


class LoginForm(forms.Form):
    phone_number = phone_number_field()
    #phone_number = forms.CharField(label="Numéro de téléphone")
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)


class ResetPasswordForm(forms.Form):
    """Réinitialisation en libre-service pour un VENDEUR : identité vérifiée
    uniquement par téléphone + entreprise (pas d'email/SMS)."""

    #phone_number = forms.CharField(label="Numéro de téléphone")
    phone_number = phone_number_field()
    company = forms.ModelChoiceField(label="Entreprise", queryset=Company.objects.order_by("name"))
    new_password = forms.CharField(label="Nouveau mot de passe", widget=forms.PasswordInput, min_length=6)
    confirm_new_password = forms.CharField(label="Confirmer le mot de passe", widget=forms.PasswordInput, min_length=6)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") != cleaned.get("confirm_new_password"):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "address", "phone", "email", "website", "tva_rate"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex : NK_Imprimerie"}),
            "address": forms.TextInput(attrs={"placeholder": "Béoumi, Côte d'Ivoire"}),
            "phone": forms.TextInput(attrs={"placeholder": "0700000000"}),
            "email": forms.EmailInput(attrs={"placeholder": "contact@monentreprise.ci"}),
            "website": forms.TextInput(attrs={"placeholder": "www.monentreprise.ci"}),
        }
        labels = {
            "name": "Nom de l'entreprise", "address": "Adresse", "phone": "Téléphone",
            "email": "Email", "website": "Site web", "tva_rate": "Taux de TVA (%)",
        }


class CompanyLogoForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["logo"]


class CompanyStampForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["stamp"]


class CreateUserForm(forms.Form):
    """Création d'un vendeur ou d'un administrateur par l'ADMIN."""

    full_name = forms.CharField(label="Nom complet", min_length=2)
    phone_number = phone_number_field(label="Téléphone (identifiant)")
    #phone_number = forms.CharField(label="Téléphone (identifiant)", min_length=6)
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput, min_length=6)
    confirm_password = forms.CharField(label="Confirmer", widget=forms.PasswordInput, min_length=6)
    role = forms.ChoiceField(label="Rôle", choices=User.Role.choices)
    company = forms.ModelChoiceField(
        label="Entreprise", queryset=Company.objects.order_by("name"), required=False
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        phone = cleaned.get("phone_number")
        if phone and User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà utilisé.")
        if cleaned.get("role") == User.Role.SELLER and not cleaned.get("company"):
            raise forms.ValidationError("Un vendeur doit être rattaché à une entreprise.")
        return cleaned


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "description", "price", "stock", "critical_threshold"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex : Disque de frein ventilé"}),
            "description": forms.Textarea(attrs={"placeholder": "Détails optionnels du produit", "rows": 3}),
            "price": forms.NumberInput(attrs={"placeholder": "Ex : 15000"}),
            "stock": forms.NumberInput(attrs={"placeholder": "Ex : 20"}),
            "critical_threshold": forms.NumberInput(attrs={"placeholder": "Ex : 5"}),
        }

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("Le prix unitaire doit être positif.")
        return price

    def clean_stock(self):
        stock = self.cleaned_data["stock"]
        if stock < 0:
            raise forms.ValidationError("Le stock ne peut pas être négatif.")
        return stock


class ProductImportForm(forms.Form):
    """Import en masse de produits depuis un fichier Excel (.xlsx)."""

    file = forms.FileField(label="Fichier Excel (.xlsx)")

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Le fichier doit être au format .xlsx (Excel).")
        return f


class CashSessionOpenForm(forms.Form):
    planned_closed_at = forms.DateTimeField(
        label="Date/Heure Fermeture",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"],
    )


class CashSessionExtendForm(forms.Form):
    planned_closed_at = forms.DateTimeField(
        label="Nouvelle Date/Heure Fermeture",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"],
    )


class AddToCartForm(forms.Form):
    """Ajout d'un produit au panier (Caisse) : une ligne de ce formulaire par produit affiché."""

    product_id = forms.CharField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, initial=1)
    is_gift = forms.BooleanField(required=False, label="Offert")


class ValidateSaleForm(forms.Form):
    """Informations complémentaires saisies au moment de valider la vente."""

    client_name = forms.CharField(label="Nom du client", required=True )
    client_phone = forms.CharField(label="Téléphone du client", required=False)
    notes = forms.CharField(label="Notes", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    discount_type = forms.ChoiceField(label="Type de réduction", choices=DiscountType.choices, required=False)
    discount_value = forms.FloatField(label="Valeur de la réduction", required=False, min_value=0)
