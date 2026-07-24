# Vues Django (MVT) du Facturier Automatique : authentification, entreprises
# (multi-tenant), vendeurs, produits (+ import Excel), Caisse (panier en
# session), session de caisse, historique, facture (HTML + PDF).

from django.core.paginator import Paginator

from datetime import datetime, time

from django.db import transaction
from django.db.models import F, ProtectedError

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import admin_required, seller_required
from .forms import (
    AddToCartForm,
    CashSessionExtendForm,
    CashSessionOpenForm,
    CompanyForm,
    CompanyLogoForm,
    CompanyStampForm,
    CreateUserForm,
    LoginForm,
    ProductForm,
    ProductImportForm,
    ResetPasswordForm,
    ValidateSaleForm,
)
from .helpers import get_active_company
from .invoice_pdf import build_invoice_pdf
from .models import (
    CashSession, Company, DiscountType, PaymentMethod, Product, Sale, SaleItem, SalePayment, User,
)
from .product_import import build_import_template, parse_products_file

ROUNDING_TOLERANCE = 1  # F CFA - tolère les écarts d'arrondi d'affichage
PAYMENT_METHOD_LABELS = dict(PaymentMethod.choices)


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect("caisse")

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["phone_number"],
            password=form.cleaned_data["password"],
        )
        if user is None:
            messages.error(request, "Identifiants incorrects.")
        else:
            login(request, user)
            return redirect("caisse")

    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


def reset_password_view(request):
    """Réinitialisation en libre-service pour un VENDEUR : identité vérifiée
    uniquement par téléphone + entreprise (pas d'email/SMS)."""
    form = ResetPasswordForm(request.POST or None)
    success = False

    if request.method == "POST" and form.is_valid():
        try:
            user = User.objects.get(
                phone_number=form.cleaned_data["phone_number"],
                company=form.cleaned_data["company"],
                role=User.Role.SELLER,
            )
        except User.DoesNotExist:
            messages.error(request, "Numéro de téléphone ou entreprise incorrect.")
        else:
            user.set_password(form.cleaned_data["new_password"])
            user.save(update_fields=["password"])
            success = True

    return render(request, "core/reset_password.html", {"form": form, "success": success})


@login_required
def switch_company_view(request):
    """Change l'entreprise active de l'ADMIN (mémorisée en session)."""
    if request.user.role == User.Role.ADMIN and request.method == "POST":
        company_id = request.POST.get("company_id")
        if Company.objects.filter(id=company_id).exists():
            request.session["active_company_id"] = company_id
    return redirect(request.POST.get("next") or "dashboard")


# ---------------------------------------------------------------------------
# Dashboard (ADMIN)
# ---------------------------------------------------------------------------

@admin_required
def dashboard_view(request):
    company = get_active_company(request)
    if not company:
        return render(request, "core/dashboard.html", {"company": None})

    start_of_day = timezone.make_aware(datetime.combine(timezone.now().date(), time.min))
    today_sales = Sale.objects.filter(company=company, created_at__gte=start_of_day)
    revenue_today = sum(s.total for s in today_sales)

    low_stock_products = [
        p for p in Product.objects.filter(company=company).order_by("stock")
        if p.stock <= p.critical_threshold
    ]

    return render(request, "core/dashboard.html", {
        "company": company,
        "revenue_today": revenue_today,
        "sales_count_today": today_sales.count(),
        "low_stock_products": low_stock_products,
    })


# ---------------------------------------------------------------------------
# Entreprises (multi-tenant)
# ---------------------------------------------------------------------------

@admin_required
def companies_list_view(request):
    companies = Company.objects.all()
    form = CompanyForm(request.POST or None)

    if request.method == "POST" and "create_company" in request.POST and form.is_valid():
        company = form.save()
        request.session["active_company_id"] = str(company.id)
        messages.success(request, "Entreprise créée avec succès.")
        return redirect("company_edit", company_id=company.id)

    return render(request, "core/companies_list.html", {"companies": companies, "form": form})


@admin_required
def company_edit_view(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    form = CompanyForm(request.POST or None, instance=company)
    logo_form = CompanyLogoForm(request.POST or None, request.FILES or None, instance=company)
    stamp_form = CompanyStampForm(request.POST or None, request.FILES or None, instance=company)

    if request.method == "POST":
        if "save_info" in request.POST and form.is_valid():
            form.save()
            messages.success(request, "Informations enregistrées avec succès.")
            return redirect("company_edit", company_id=company.id)
        if "upload_logo" in request.POST and logo_form.is_valid():
            logo_form.save()
            messages.success(request, "Logo mis à jour.")
            return redirect("company_edit", company_id=company.id)
        if "upload_stamp" in request.POST and stamp_form.is_valid():
            stamp_form.save()
            messages.success(request, "Cachet mis à jour.")
            return redirect("company_edit", company_id=company.id)

    return render(request, "core/company_form.html", {
        "company": company, "form": form, "logo_form": logo_form, "stamp_form": stamp_form,
    })


@admin_required
def company_delete_view(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == "POST":
        if company.products.exists() or company.sales.exists():
            messages.error(request, "Impossible de supprimer une entreprise ayant déjà des produits ou des ventes.")
        else:
            company.delete()
            messages.success(request, "Entreprise supprimée.")
    return redirect("companies_list")


# ---------------------------------------------------------------------------
# Vendeurs
# ---------------------------------------------------------------------------

@admin_required
def users_list_view(request):
    users = User.objects.all().order_by("full_name")
    companies = Company.objects.order_by("name")
    form = CreateUserForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        User.objects.create_user(
            phone_number=form.cleaned_data["phone_number"],
            full_name=form.cleaned_data["full_name"],
            password=form.cleaned_data["password"],
            role=form.cleaned_data["role"],
            company=form.cleaned_data.get("company"),
        )
        messages.success(request, "Compte créé avec succès.")
        return redirect("users_list")

    return render(request, "core/users_list.html", {"users": users, "companies": companies, "form": form})




@admin_required
def user_delete_view(request, user_id):
    """Supprime un compte (vendeur ou administrateur). Un compte ayant déjà
    des ventes enregistrées ne peut pas être supprimé (intégrité de
    l'historique) : on lui suggère de désactiver le compte à la place."""
    target_user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        if target_user.id == request.user.id:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        else:
            try:
                target_user.delete()
                messages.success(request, "Compte supprimé avec succès.")
            except ProtectedError:
                messages.error(
                    request,
                    f"Impossible de supprimer « {target_user.full_name} » : des ventes sont déjà "
                    "enregistrées à son nom. Désactivez plutôt ce compte.",
                )

    return redirect("users_list")


@admin_required
def user_deactivate_view(request, user_id):
    """Désactive (ou réactive) un compte sans supprimer son historique de
    ventes. Alternative à la suppression quand celle-ci est impossible."""
    target_user = get_object_or_404(User, id=user_id)
    if request.method == "POST" and target_user.id != request.user.id:
        target_user.is_active = not target_user.is_active
        target_user.save(update_fields=["is_active"])
        messages.success(
            request,
            f"Compte {'réactivé' if target_user.is_active else 'désactivé'} avec succès.",
        )
    return redirect("users_list")
# ---------------------------------------------------------------------------
# Produits (+ import Excel)
# ---------------------------------------------------------------------------

@admin_required
def products_list_view(request):
    company = get_active_company(request)
    if not company:
        return render(request, "core/products_list.html", {"company": None})

    query = request.GET.get("q", "").strip()
    products = Product.objects.filter(company=company)
    if query:
        products = products.filter(name__icontains=query)

    form = ProductForm(request.POST or None)
    if request.method == "POST" and "create_product" in request.POST and form.is_valid():
        product = form.save(commit=False)
        product.company = company
        product.save()
        messages.success(request, "Produit ajouté avec succès.")
        return redirect("products_list")

    return render(request, "core/products_list.html", {
        "company": company, "products": products, "form": form, "query": query,
    })


@admin_required
def product_edit_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Produit modifié avec succès.")
        return redirect("products_list")
    return render(request, "core/product_form.html", {"product": product, "form": form})


@admin_required
def product_delete_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Produit supprimé.")
    return redirect("products_list")


@admin_required
def product_import_view(request):
    """Import en masse de produits depuis un fichier Excel (.xlsx)."""
    company = get_active_company(request)
    if not company:
        messages.error(request, "Créez d'abord une entreprise avant d'importer des produits.")
        return redirect("companies_list")

    form = ProductImportForm(request.POST or None, request.FILES or None)
    result = None

    if request.method == "POST" and form.is_valid():
        products_to_create, errors = parse_products_file(form.cleaned_data["file"], company)
        if products_to_create:
            Product.objects.bulk_create(products_to_create)
        result = {"created": len(products_to_create), "errors": errors}
        if products_to_create:
            messages.success(request, f"{len(products_to_create)} produit(s) importé(s) avec succès.")
        if errors:
            messages.warning(request, f"{len(errors)} ligne(s) n'ont pas pu être importées (voir détail ci-dessous).")

    return render(request, "core/product_import.html", {"company": company, "form": form, "result": result})


@admin_required
def product_import_template_view(request):
    """Télécharge un modèle Excel vierge avec les bons en-têtes de colonnes."""
    buffer = build_import_template()
    response = FileResponse(buffer, as_attachment=True, filename="modele_import_produits.xlsx")
    return response


# ---------------------------------------------------------------------------
# Caisse (panier stocké en session) + session de caisse
# ---------------------------------------------------------------------------

def _get_cart(request):
    return request.session.setdefault("cart", {})


def _save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def _get_active_cash_session(user):
    session = CashSession.objects.filter(seller=user, is_closed=False).first()
    if session and timezone.now() >= session.planned_closed_at:
        session.is_closed = True
        session.actual_closed_at = session.planned_closed_at
        session.save(update_fields=["is_closed", "actual_closed_at"])
        return None
    return session


@login_required
def cash_session_open_view(request):
    if request.user.role != User.Role.SELLER:
        return redirect("dashboard")
    if not request.user.company_id:
        messages.error(request, "Ce vendeur n'est associé à aucune entreprise.")
        return redirect("logout")
    if _get_active_cash_session(request.user):
        return redirect("caisse")

    form = CashSessionOpenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        planned_closed_at = form.cleaned_data["planned_closed_at"]
        if timezone.is_naive(planned_closed_at):
            planned_closed_at = timezone.make_aware(planned_closed_at)
        if planned_closed_at <= timezone.now():
            messages.error(request, "La fermeture doit être postérieure à l'ouverture.")
        else:
            CashSession.objects.create(
                company=request.user.company,
                seller=request.user,
                opened_at=timezone.now(),
                planned_closed_at=planned_closed_at,
            )
            return redirect("caisse")

    return render(request, "core/cash_session_open.html", {"form": form})


@seller_required
def cash_session_extend_view(request):
    session = _get_active_cash_session(request.user)
    if not session:
        return redirect("cash_session_open")

    form = CashSessionExtendForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        planned_closed_at = form.cleaned_data["planned_closed_at"]
        if timezone.is_naive(planned_closed_at):
            planned_closed_at = timezone.make_aware(planned_closed_at)
        if planned_closed_at <= timezone.now():
            messages.error(request, "La nouvelle heure de fermeture doit être dans le futur.")
        else:
            session.planned_closed_at = planned_closed_at
            session.save(update_fields=["planned_closed_at"])
            messages.success(request, "Fermeture prolongée avec succès.")
            return redirect("caisse")

    return render(request, "core/cash_session_extend.html", {"form": form, "session": session})


@seller_required
def cash_session_close_view(request):
    session = _get_active_cash_session(request.user)
    if session and request.method == "POST":
        session.is_closed = True
        session.actual_closed_at = timezone.now()
        session.save(update_fields=["is_closed", "actual_closed_at"])
    return redirect("logout")


@login_required
def caisse_view(request):
    is_admin = request.user.role == User.Role.ADMIN

    # Un Vendeur doit avoir une session de caisse ouverte et non expirée
    cash_session = None
    if not is_admin:
        cash_session = _get_active_cash_session(request.user)
        if not cash_session:
            return redirect("cash_session_open")

    company = get_active_company(request)
    if not company:
        return render(request, "core/caisse.html", {"company": None, "is_admin": is_admin})

    query = request.GET.get("q", "").strip()
    products = Product.objects.filter(company=company)
    if query:
        products = products.filter(name__icontains=query)

    paginator = Paginator(products, 15)
    page_number = request.GET.get("page", 1)
    products_page = paginator.get_page(page_number)

    cart = _get_cart(request)

    # --- Traitement des actions du panier (une seule vue gère tout, via le champ "action") ---
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_to_cart":
            form = AddToCartForm(request.POST)
            if form.is_valid():
                product = get_object_or_404(Product, id=form.cleaned_data["product_id"], company=company)
                quantity = min(form.cleaned_data["quantity"], product.stock) if product.stock > 0 else 0
                if quantity > 0:
                    cart[str(product.id)] = {
                        "quantity": quantity, "is_gift": form.cleaned_data["is_gift"], "discount": 0,
                    }
                    _save_cart(request, cart)
                else:
                    messages.error(request, f"« {product.name} » est en rupture de stock.")
            return redirect(_caisse_redirect_url(request))

        if action == "remove_from_cart":
            product_id = request.POST.get("product_id")
            cart.pop(product_id, None)
            _save_cart(request, cart)
            return redirect(_caisse_redirect_url(request))

        if action == "update_line_discount":
            product_id = request.POST.get("product_id")
            if product_id in cart:
                try:
                    line_discount = max(0, float(request.POST.get("discount_amount") or 0))
                except ValueError:
                    line_discount = 0
                cart[product_id]["discount"] = line_discount
                _save_cart(request, cart)
            return redirect(_caisse_redirect_url(request))

        if action == "clear_cart":
            _save_cart(request, {})
            return redirect("caisse")

        if action == "validate_sale":
            return _handle_validate_sale(request, company, cart, cash_session)

    # --- Construction du récapitulatif du panier pour l'affichage ---
    cart_lines = []
    sub_total = 0
    for product_id, line in cart.items():
        product = Product.objects.filter(id=product_id, company=company).first()
        if not product:
            continue
        line_discount = line.get("discount", 0)
        raw_total = product.price * line["quantity"]
        line_total = 0 if line["is_gift"] else max(0, raw_total - line_discount)
        sub_total += line_total
        cart_lines.append({
            "product": product, "quantity": line["quantity"], "is_gift": line["is_gift"],
            "discount": line_discount, "raw_total": raw_total, "line_total": line_total,
        })

    sale_form = ValidateSaleForm(request.POST if request.method == "POST" else None)
    discount_type = request.POST.get("discount_type", "NONE") if request.method == "POST" else "NONE"
    try:
        discount_value = float(request.POST.get("discount_value") or 0) if request.method == "POST" else 0
    except ValueError:
        discount_value = 0

    if discount_type == DiscountType.PERCENTAGE:
        discount_amount = min(sub_total, sub_total * (discount_value / 100))
    elif discount_type == DiscountType.AMOUNT:
        discount_amount = min(sub_total, discount_value)
    else:
        discount_amount = 0

    taxable = sub_total - discount_amount
    tva_amount = taxable * (company.tva_rate / 100)
    total = taxable + tva_amount

    start_of_day = timezone.make_aware(datetime.combine(timezone.now().date(), time.min))
    seller_sales_today = Sale.objects.filter(company=company, created_at__gte=start_of_day)
    if not is_admin:
        seller_sales_today = seller_sales_today.filter(seller=request.user)
    revenue_today = sum(s.total for s in seller_sales_today)

    return render(request, "core/caisse.html", {
        "company": company,
        "is_admin": is_admin,
        "products": products_page,
        "query": query,
        "cart_lines": cart_lines,
        "sub_total": sub_total,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "discount_amount": discount_amount,
        "tva_amount": tva_amount,
        "total": total,
        "payment_methods": PaymentMethod.choices,
        "cash_session": cash_session,
        "revenue_today": revenue_today,
        "sales_count_today": seller_sales_today.count(),
    })

def _handle_validate_sale(request, company, cart, cash_session):
    if not cart:
        messages.error(request, "Le panier est vide.")
        return redirect("caisse")

    if request.user.role == User.Role.SELLER:
        if not cash_session:
            messages.error(request, "Aucune session de caisse ouverte.")
            return redirect("cash_session_open")
        if timezone.now() >= cash_session.planned_closed_at:
            messages.error(request, "La session de caisse est arrivée à échéance.")
            return redirect("cash_session_open")

    payment_methods = request.POST.getlist("payment_method")
    payment_amounts = request.POST.getlist("payment_amount")
    payments = []
    for method, amount_raw in zip(payment_methods, payment_amounts):
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            payments.append({"method": method, "amount": amount})

    if not payments:
        messages.error(request, "Sélectionnez au moins un mode de paiement.")
        return redirect("caisse")

    discount_type = request.POST.get("discount_type", DiscountType.NONE)
    try:
        discount_value = float(request.POST.get("discount_value") or 0)
    except ValueError:
        discount_value = 0

    try:
        with transaction.atomic():
            sub_total = 0
            resolved_items = []

            for product_id, line in cart.items():
                product = Product.objects.select_for_update().get(id=product_id, company=company)
                quantity = line["quantity"]
                is_gift = line["is_gift"]
                line_discount = max(0, min(line.get("discount", 0), product.price * quantity))

                if quantity > product.stock:
                    raise ValueError(
                        f'Stock insuffisant pour "{product.name}" '
                        f"(demandé: {quantity}, disponible: {product.stock})."
                    )
                if not is_gift:
                    sub_total += max(0, product.price * quantity - line_discount)
                resolved_items.append((product, quantity, is_gift, line_discount))

            if discount_type == DiscountType.PERCENTAGE:
                discount_amount = sub_total * (discount_value / 100)
            elif discount_type == DiscountType.AMOUNT:
                discount_amount = discount_value
            else:
                discount_amount = 0
            discount_amount = max(0, min(discount_amount, sub_total))

            taxable = sub_total - discount_amount
            tva_amount = taxable * (company.tva_rate / 100)
            total = taxable + tva_amount

            payments_sum = sum(p["amount"] for p in payments)
            if abs(payments_sum - total) > ROUNDING_TOLERANCE:
                raise ValueError(
                    f"Le total des paiements ({round(payments_sum)} F CFA) ne correspond pas "
                    f"au montant total de la facture ({round(total)} F CFA)."
                )

            sale = Sale.objects.create(
                company=company,
                sub_total=sub_total,
                discount_type=discount_type,
                discount_value=discount_value,
                discount_amount=discount_amount,
                tva_amount=tva_amount,
                total=total,
                client_name=request.POST.get("client_name") or None,
                client_phone=request.POST.get("client_phone") or None,
                notes=request.POST.get("notes") or None,
                seller=request.user,
            )

            for product, quantity, is_gift, line_discount in resolved_items:
                sale.items.create(
                    product=product, quantity=quantity, price=product.price,
                    is_gift=is_gift, discount_amount=line_discount,
                )
                product.stock = F("stock") - quantity
                product.save(update_fields=["stock"])

            for payment in payments:
                sale.payments.create(method=payment["method"], amount=payment["amount"])

    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("caisse")

    _save_cart(request, {})
    messages.success(request, "Vente validée avec succès.")
    return redirect("invoice", sale_id=sale.id)


# ---------------------------------------------------------------------------
# Historique des ventes
# ---------------------------------------------------------------------------

@login_required
def sales_history_view(request):
    is_admin = request.user.role == User.Role.ADMIN
    company = get_active_company(request)
    if not company:
        return render(request, "core/sales_history.html", {"company": None, "is_admin": is_admin})

    sales = Sale.objects.filter(company=company)
    if not is_admin:
        sales = sales.filter(seller=request.user)

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    product_id = request.GET.get("product_id")

    if request.GET.get("today") == "1":
        today_str = timezone.now().date().isoformat()
        start_date = end_date = today_str

    if start_date:
        sales = sales.filter(created_at__date__gte=start_date)
    if end_date:
        sales = sales.filter(created_at__date__lte=end_date)
    if product_id:
        sales = sales.filter(items__product_id=product_id).distinct()

    total_periode = sum(s.total for s in sales)
    products = Product.objects.filter(company=company)

    return render(request, "core/sales_history.html", {
        "company": company, "is_admin": is_admin, "sales": sales, "products": products,
        "start_date": start_date or "", "end_date": end_date or "", "product_id": product_id or "",
        "total_periode": total_periode,
    })


# ---------------------------------------------------------------------------
# Facture (HTML imprimable + PDF)
# ---------------------------------------------------------------------------

@login_required
@login_required
def invoice_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    items_display = []
    for item in sale.items.all():
        raw_amount = item.price * item.quantity
        net_amount = 0 if item.is_gift else max(0, raw_amount - item.discount_amount)
        items_display.append({"item": item, "net_amount": net_amount})
    return render(request, "core/invoice.html", {
        "sale": sale, "company": sale.company, "items_display": items_display,
    })

@login_required
def invoice_pdf_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    pdf_buffer = build_invoice_pdf(sale, sale.company)
    return FileResponse(
        pdf_buffer, content_type="application/pdf", filename=f"facture-{sale.invoice_number}.pdf"
    )
