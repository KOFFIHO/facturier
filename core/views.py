# Vues Django (MVT) du Facturier Automatique : authentification, entreprises
# (multi-tenant), vendeurs, produits (+ import Excel), Caisse (panier en
# session), session de caisse, historique, facture (HTML + PDF).
import uuid
from django.core.paginator import Paginator

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import F, Q, ProtectedError, Sum

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import admin_required, seller_required, manager_required
from .forms import (
    AddToCartForm,
    ApprovisionnementForm,
    CashSessionExtendForm,
    CashSessionOpenForm,
    CompanyForm,
    CompanyLogoForm,
    CompanyStampForm,
    CreateUserForm,
    DepenseForm,
    LoginForm,
    ProductForm,
    ProductImportForm,
    ResetPasswordForm,
    ServiceForm,
    ValidateSaleForm,
)
from .helpers import get_active_company
from .invoice_pdf import build_invoice_pdf
from .models import (
    Approvisionnement, CashSession, Company, Depense, DiscountType, PaymentMethod, Product, Sale, SaleItem, SalePayment, User,Service, SaleType
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
def _month_bounds(d):
    start = d.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    end = next_month - timedelta(days=1)
    return start, end


def _last_12_month_starts(today):
    months = []
    y, m = today.year, today.month
    for i in range(11, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append(date(yy, mm, 1))
    return months

@admin_required
@admin_required
def dashboard_view(request):
    company = get_active_company(request)
    if not company:
        return render(request, "core/dashboard.html", {"company": None})

    today = timezone.now().date()
    start_of_day = timezone.make_aware(datetime.combine(today, time.min))
    month_start, month_end = _month_bounds(today)
    year_start = today.replace(month=1, day=1)

    sales_today = Sale.objects.filter(company=company, created_at__gte=start_of_day)
    revenue_today = sum(s.total for s in sales_today)

    sales_month = Sale.objects.filter(company=company, created_at__date__gte=month_start, created_at__date__lte=month_end)
    revenue_month = sales_month.aggregate(Sum("total"))["total__sum"] or 0

    sales_year = Sale.objects.filter(company=company, created_at__date__gte=year_start)
    revenue_year = sales_year.aggregate(Sum("total"))["total__sum"] or 0

    depenses_month = Depense.objects.filter(company=company, date__gte=month_start, date__lte=month_end)
    expenses_month = depenses_month.aggregate(Sum("amount"))["amount__sum"] or 0

    depenses_year = Depense.objects.filter(company=company, date__gte=year_start)
    expenses_year = depenses_year.aggregate(Sum("amount"))["amount__sum"] or 0

    profit_month = revenue_month - expenses_month
    profit_year = revenue_year - expenses_year

    services_today_count = SaleItem.objects.filter(
        sale__company=company, sale__created_at__gte=start_of_day, product__isnull=True,
    ).count()

    low_stock_products = [
        p for p in Product.objects.filter(company=company).order_by("stock")
        if p.stock <= p.critical_threshold
    ]

    # --- Graphique 1 : évolution du CA sur les 12 derniers mois ---
    month_starts = _last_12_month_starts(today)
    monthly_series = []
    for m_start in month_starts:
        _, m_end = _month_bounds(m_start)
        total = Sale.objects.filter(
            company=company, created_at__date__gte=m_start, created_at__date__lte=m_end
        ).aggregate(Sum("total"))["total__sum"] or 0
        monthly_series.append({"label": m_start.strftime("%Y-%m"), "value": total})

    chart_width, chart_height = 700, 220
    max_value = max([m["value"] for m in monthly_series] + [1])
    n = len(monthly_series)
    step_x = chart_width / (n - 1) if n > 1 else 0
    points = []
    for i, m in enumerate(monthly_series):
        x = i * step_x
        y = chart_height - (m["value"] / max_value * chart_height)
        m["x"] = round(x, 1)
        m["y"] = round(y, 1)
        points.append(f"{x:.1f},{y:.1f}")
    revenue_polyline_points = " ".join(points)

    # --- Graphique 2 : CA du mois par type de vente (Produits / Services) ---
    items_month = SaleItem.objects.filter(sale__in=sales_month)
    ca_products_month = 0
    ca_services_month = 0
    for item in items_month:
        raw = item.price * item.quantity
        net = 0 if item.is_gift else max(0, raw - item.discount_amount)
        if item.product_id:
            ca_products_month += net
        else:
            ca_services_month += net
    max_type_value = max(ca_products_month, ca_services_month, 1)
    bar_max_height = 180
    product_bar_height = round((ca_products_month / max_type_value) * bar_max_height, 1)
    service_bar_height = round((ca_services_month / max_type_value) * bar_max_height, 1)
    product_bar_y: float = 20 + (bar_max_height - product_bar_height)
    service_bar_y: float = 20 + (bar_max_height - service_bar_height)

    return render(request, "core/dashboard.html", {
        "company": company,
        "revenue_today": revenue_today,
        "revenue_month": revenue_month,
        "expenses_month": expenses_month,
        "profit_month": profit_month,
        "profit_year": profit_year,
        "services_today_count": services_today_count,
        "low_stock_products": low_stock_products,
        "monthly_series": monthly_series,
        "revenue_polyline_points": revenue_polyline_points,
        "chart_width": chart_width,
        "chart_height": chart_height,
        "ca_products_month": ca_products_month,
        "ca_services_month": ca_services_month,
        "product_bar_height": product_bar_height,
        "service_bar_height": service_bar_height,
        "bar_max_height": bar_max_height,
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

def _get_cart(request):
    return request.session.setdefault("cart", {})


def _save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def _caisse_redirect_url(request):
    """Conserve les paramètres de recherche/pagination lors de la redirection dans la caisse."""
    q = request.POST.get("q") or request.GET.get("q", "")
    page = request.POST.get("page") or request.GET.get("page", "")
    
    url = redirect("caisse").url
    params = []
    if q:
        params.append(f"q={q}")
    if page:
        params.append(f"page={page}")
    
    if params:
        url += "?" + "&".join(params)
    return url
# ---------------------------------------------------------------------------
# Produits (+ import Excel)
# ---------------------------------------------------------------------------

@manager_required
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
@manager_required
def product_edit_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Produit modifié avec succès.")
        return redirect("products_list")
    return render(request, "core/product_form.html", {"product": product, "form": form})


@admin_required
@manager_required
def product_delete_view(request, product_id):
    """Supprime un produit. Si des approvisionnements ou des ventes y font
    déjà référence, la suppression est bloquée (intégrité de l'historique)."""
    product = get_object_or_404(Product, id=product_id)
    if request.method == "POST":
        try:
            product.delete()
            messages.success(request, "Produit supprimé.")
        except ProtectedError:
            messages.error(
                request,
                f"Impossible de supprimer « {product.name} » : des approvisionnements ou des ventes "
                "y font déjà référence. Vous pouvez modifier son stock à 0 à la place.",
            )
    return redirect("products_list")


@admin_required
@manager_required
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
@manager_required
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

def _get_cart(request):
    return request.session.setdefault("cart", {})


def _save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def _flash_caisse_form(request):
    methods = request.POST.getlist("payment_method")
    request.session["caisse_form_data"] = {
        "client_name": request.POST.get("client_name", ""),
        "client_phone": request.POST.get("client_phone", ""),
        "notes": request.POST.get("notes", ""),
        "discount_type": request.POST.get("discount_type", "NONE"),
        "discount_value": request.POST.get("discount_value", "0"),
        "payment_amounts": {m: request.POST.get(f"payment_amount_{m}", "") for m in methods},
    }


@login_required
def caisse_view(request):
    """Caisse unique : un même panier peut combiner des produits (avec
    gestion de stock) et des prestations de services (catalogue ou ligne
    libre, prix non fixe) — pour qu'un patient reçoive UNE SEULE facture
    couvrant à la fois consultation/injection et achats en pharmacie."""
    is_admin = request.user.role == User.Role.ADMIN

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
    products_paginator = Paginator(products, 3)
    products_page = products_paginator.get_page(request.GET.get("page", 1))

    services = Service.objects.filter(company=company, is_active=True)
    services_paginator = Paginator(services, 3)
    services_page = services_paginator.get_page(request.GET.get("spage", 1))

    cart = _get_cart(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_product":
            form = AddToCartForm(request.POST)
            if form.is_valid():
                product = get_object_or_404(Product, id=form.cleaned_data["product_id"], company=company)
                quantity = min(form.cleaned_data["quantity"], product.stock) if product.stock > 0 else 0
                if quantity > 0:
                    cart[uuid.uuid4().hex] = {
                        "kind": "product", "ref_id": str(product.id), "label": product.name,
                        "price": product.price, "quantity": quantity,
                        "is_gift": form.cleaned_data["is_gift"], "discount": 0,
                    }
                    _save_cart(request, cart)
                else:
                    messages.error(request, f"« {product.name} » est en rupture de stock.")
            return redirect("caisse")

        if action == "add_service":
            service = get_object_or_404(Service, id=request.POST.get("service_id"), company=company)
            try:
                price = max(0, float(request.POST.get("price") or service.default_price))
                quantity = max(1, int(request.POST.get("quantity") or 1))
            except ValueError:
                messages.error(request, "Prix ou quantité invalide.")
                return redirect("caisse")
            cart[uuid.uuid4().hex] = {
                "kind": "service", "ref_id": str(service.id), "label": service.name,
                "price": price, "quantity": quantity, "is_gift": False, "discount": 0,
            }
            _save_cart(request, cart)
            return redirect("caisse")

        if action == "add_free_line":
            label = (request.POST.get("label") or "").strip()
            if not label:
                messages.error(request, "La désignation de la prestation est requise.")
                return redirect("caisse")
            try:
                price = max(0, float(request.POST.get("price") or 0))
                quantity = max(1, int(request.POST.get("quantity") or 1))
            except ValueError:
                messages.error(request, "Prix ou quantité invalide.")
                return redirect("caisse")
            cart[uuid.uuid4().hex] = {
                "kind": "free", "ref_id": None, "label": label,
                "price": price, "quantity": quantity, "is_gift": False, "discount": 0,
            }
            _save_cart(request, cart)
            return redirect("caisse")

        if action == "remove_line":
            cart.pop(request.POST.get("line_id"), None)
            _save_cart(request, cart)
            return redirect("caisse")

        if action == "update_line_discount":
            line_id = request.POST.get("line_id")
            if line_id in cart:
                try:
                    cart[line_id]["discount"] = max(0, float(request.POST.get("discount_amount") or 0))
                except ValueError:
                    cart[line_id]["discount"] = 0
                _save_cart(request, cart)
            return redirect("caisse")

        if action == "clear_cart":
            _save_cart(request, {})
            return redirect("caisse")

        if action == "validate_sale":
            return _handle_validate_sale(request, company, cart, cash_session)

    cart_lines = []
    sub_total = 0
    for line_id, line in cart.items():
        raw_total = line["price"] * line["quantity"]
        line_total = 0 if line["is_gift"] else max(0, raw_total - line.get("discount", 0))
        sub_total += line_total
        cart_lines.append({
            "line_id": line_id, "kind": line["kind"], "label": line["label"], "price": line["price"],
            "quantity": line["quantity"], "is_gift": line["is_gift"], "discount": line.get("discount", 0),
            "raw_total": raw_total, "line_total": line_total,
        })

    flash = request.session.pop("caisse_form_data", None) or {}
    discount_type = flash.get("discount_type", "NONE")
    try:
        discount_value = float(flash.get("discount_value") or 0)
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
        "company": company, "is_admin": is_admin,
        "products": products_page, "query": query, "services": services_page,
        "cart_lines": cart_lines, "sub_total": sub_total,
        "discount_type": discount_type, "discount_value": discount_value,
        "discount_amount": discount_amount, "tva_amount": tva_amount, "total": total,
        "payment_methods": PaymentMethod.choices, "cash_session": cash_session,
        "revenue_today": revenue_today, "sales_count_today": seller_sales_today.count(),
        "client_name_value": flash.get("client_name", ""),
        "client_phone_value": flash.get("client_phone", ""),
        "notes_value": flash.get("notes", ""),
        "selected_payments": flash.get("payment_amounts", {}),
    })


def _handle_validate_sale(request, company, cart, cash_session):
    """Valide une vente pouvant combiner produits (stock décrémenté) et
    prestations (catalogue ou ligne libre, sans stock) sur UNE SEULE facture."""
    if not cart:
        messages.error(request, "Le panier est vide.")
        return redirect("caisse")

    if request.user.role == User.Role.SELLER:
        if not cash_session:
            messages.error(request, "Aucune session de caisse ouverte. Veuillez ouvrir votre caisse avant de vendre.")
            return redirect("cash_session_open")
        if timezone.now() >= cash_session.planned_closed_at:
            messages.error(request, "La session de caisse est arrivée à échéance. Veuillez la clôturer ou la prolonger.")
            return redirect("cash_session_open")

    payments = []
    for method in request.POST.getlist("payment_method"):
        try:
            amount = float(request.POST.get(f"payment_amount_{method}"))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            payments.append({"method": method, "amount": amount})

    if not payments:
        _flash_caisse_form(request)
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
            resolved = []
            has_product, has_service = False, False

            for line in cart.values():
                if line["kind"] == "product":
                    product = Product.objects.select_for_update().get(id=line["ref_id"], company=company)
                    if line["quantity"] > product.stock:
                        raise ValueError(
                            f'Stock insuffisant pour "{product.name}" '
                            f"(demandé: {line['quantity']}, disponible: {product.stock})."
                        )
                    has_product = True
                else:
                    product = None
                    has_service = True

                raw_total = line["price"] * line["quantity"]
                line_discount = max(0, min(line.get("discount", 0), raw_total))
                if not line["is_gift"]:
                    sub_total += max(0, raw_total - line_discount)
                resolved.append((line, product, line_discount))

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

            if has_product and has_service:
                sale_type = SaleType.MIXED
            elif has_service:
                sale_type = SaleType.SERVICE
            else:
                sale_type = SaleType.PRODUCT

            sale = Sale.objects.create(
                company=company, sale_type=sale_type,
                sub_total=sub_total, discount_type=discount_type, discount_value=discount_value,
                discount_amount=discount_amount, tva_amount=tva_amount, total=total,
                client_name=request.POST.get("client_name") or None,
                client_phone=request.POST.get("client_phone") or None,
                notes=request.POST.get("notes") or None,
                seller=request.user,
            )

            for line, product, line_discount in resolved:
                service = None
                if line["kind"] == "service" and line.get("ref_id"):
                    service = Service.objects.filter(id=line["ref_id"], company=company).first()
                sale.items.create(
                    product=product, service=service,
                    label="" if product else line["label"],
                    quantity=line["quantity"], price=line["price"],
                    is_gift=line["is_gift"], discount_amount=line_discount,
                )
                if product:
                    product.stock = F("stock") - line["quantity"]
                    product.save(update_fields=["stock"])

            for payment in payments:
                sale.payments.create(method=payment["method"], amount=payment["amount"])

    except ValueError as exc:
        _flash_caisse_form(request)
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
        pdf_buffer, content_type="application/pdf",
        filename=f"facture-{sale.invoice_number}.pdf",
        as_attachment=True,
    )


def _get_service_cart(request):
    return request.session.setdefault("service_cart", {})


def _save_service_cart(request, cart):
    request.session["service_cart"] = cart
    request.session.modified = True


@login_required
def caisse_services_view(request):
    """Caisse SERVICES : vente de prestations, depuis le catalogue ou en
    ligne libre (désignation + prix saisis à la volée). Aucun stock n'est
    décrémenté, et le prix reste modifiable à chaque vente."""
    is_admin = request.user.role == User.Role.ADMIN

    cash_session = None
    if not is_admin:
        cash_session = _get_active_cash_session(request.user)
        if not cash_session:
            return redirect("cash_session_open")

    company = get_active_company(request)
    if not company:
        return render(request, "core/caisse_services.html", {"company": None, "is_admin": is_admin})

    services = Service.objects.filter(company=company, is_active=True)
    cart = _get_service_cart(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_service":
            service = get_object_or_404(Service, id=request.POST.get("service_id"), company=company)
            try:
                price = max(0, float(request.POST.get("price") or service.default_price))
                quantity = max(1, int(request.POST.get("quantity") or 1))
            except ValueError:
                messages.error(request, "Prix ou quantité invalide.")
                return redirect("caisse_services")
            cart[uuid.uuid4().hex] = {
                "kind": "service", "service_id": str(service.id), "label": service.name,
                "price": price, "quantity": quantity, "discount": 0, "is_gift": False,
            }
            _save_service_cart(request, cart)
            return redirect("caisse_services")

        if action == "add_free_line":
            label = (request.POST.get("label") or "").strip()
            if not label:
                messages.error(request, "La désignation de la prestation est requise.")
                return redirect("caisse_services")
            try:
                price = max(0, float(request.POST.get("price") or 0))
                quantity = max(1, int(request.POST.get("quantity") or 1))
            except ValueError:
                messages.error(request, "Prix ou quantité invalide.")
                return redirect("caisse_services")
            cart[uuid.uuid4().hex] = {
                "kind": "free", "service_id": None, "label": label,
                "price": price, "quantity": quantity, "discount": 0, "is_gift": False,
            }
            _save_service_cart(request, cart)
            return redirect("caisse_services")

        if action == "remove_line":
            cart.pop(request.POST.get("line_id"), None)
            _save_service_cart(request, cart)
            return redirect("caisse_services")

        if action == "update_line_discount":
            line_id = request.POST.get("line_id")
            if line_id in cart:
                try:
                    cart[line_id]["discount"] = max(0, float(request.POST.get("discount_amount") or 0))
                except ValueError:
                    cart[line_id]["discount"] = 0
                _save_service_cart(request, cart)
            return redirect("caisse_services")

        if action == "clear_cart":
            _save_service_cart(request, {})
            return redirect("caisse_services")

        if action == "validate_sale":
            return _handle_validate_service_sale(request, company, cart, cash_session)

    cart_lines = []
    sub_total = 0
    for line_id, line in cart.items():
        raw_total = line["price"] * line["quantity"]
        line_total = 0 if line["is_gift"] else max(0, raw_total - line.get("discount", 0))
        sub_total += line_total
        cart_lines.append({
            "line_id": line_id, "label": line["label"], "price": line["price"],
            "quantity": line["quantity"], "discount": line.get("discount", 0),
            "raw_total": raw_total, "line_total": line_total,
        })

    flash = request.session.pop("caisse_services_form_data", None)
    discount_type = (flash or {}).get("discount_type", "NONE")
    try:
        discount_value = float((flash or {}).get("discount_value") or 0)
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
    today_sales = Sale.objects.filter(company=company, sale_type=SaleType.SERVICE, created_at__gte=start_of_day)
    if not is_admin:
        today_sales = today_sales.filter(seller=request.user)

    return render(request, "core/caisse_services.html", {
        "company": company, "is_admin": is_admin, "services": services,
        "cart_lines": cart_lines, "sub_total": sub_total,
        "discount_type": discount_type, "discount_value": discount_value,
        "discount_amount": discount_amount, "tva_amount": tva_amount, "total": total,
        "payment_methods": PaymentMethod.choices, "cash_session": cash_session,
        "revenue_today": sum(s.total for s in today_sales),
        "sales_count_today": today_sales.count(),
        "client_name_value": (flash or {}).get("client_name", ""),
        "client_phone_value": (flash or {}).get("client_phone", ""),
        "notes_value": (flash or {}).get("notes", ""),
        "selected_payments": (flash or {}).get("payment_amounts", {}),
    })


def _flash_services_form(request):
    methods = request.POST.getlist("payment_method")
    request.session["caisse_services_form_data"] = {
        "client_name": request.POST.get("client_name", ""),
        "client_phone": request.POST.get("client_phone", ""),
        "notes": request.POST.get("notes", ""),
        "discount_type": request.POST.get("discount_type", "NONE"),
        "discount_value": request.POST.get("discount_value", "0"),
        "payment_amounts": {m: request.POST.get(f"payment_amount_{m}", "") for m in methods},
    }


def _handle_validate_service_sale(request, company, cart, cash_session):
    """Validation d'une vente de services : pas de contrôle ni de
    décrémentation de stock, mais mêmes règles de réduction, de cadeau et de
    paiements combinés que la caisse Produits."""
    if not cart:
        messages.error(request, "Le panier est vide.")
        return redirect("caisse_services")

    if request.user.role == User.Role.SELLER:
        if not cash_session or timezone.now() >= cash_session.planned_closed_at:
            messages.error(request, "Session de caisse fermée ou expirée.")
            return redirect("cash_session_open")

    payments = []
    for method in request.POST.getlist("payment_method"):
        try:
            amount = float(request.POST.get(f"payment_amount_{method}"))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            payments.append({"method": method, "amount": amount})

    if not payments:
        _flash_services_form(request)
        messages.error(request, "Sélectionnez au moins un mode de paiement.")
        return redirect("caisse_services")

    discount_type = request.POST.get("discount_type", DiscountType.NONE)
    try:
        discount_value = float(request.POST.get("discount_value") or 0)
    except ValueError:
        discount_value = 0

    try:
        with transaction.atomic():
            sub_total = 0
            resolved = []
            for line in cart.values():
                raw_total = line["price"] * line["quantity"]
                line_discount = max(0, min(line.get("discount", 0), raw_total))
                if not line["is_gift"]:
                    sub_total += max(0, raw_total - line_discount)
                resolved.append((line, line_discount))

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
                company=company, sale_type=SaleType.SERVICE,
                sub_total=sub_total, discount_type=discount_type, discount_value=discount_value,
                discount_amount=discount_amount, tva_amount=tva_amount, total=total,
                client_name=request.POST.get("client_name") or None,
                client_phone=request.POST.get("client_phone") or None,
                notes=request.POST.get("notes") or None,
                seller=request.user,
            )

            for line, line_discount in resolved:
                service = None
                if line.get("service_id"):
                    service = Service.objects.filter(id=line["service_id"], company=company).first()
                sale.items.create(
                    product=None, service=service, label=line["label"],
                    quantity=line["quantity"], price=line["price"],
                    is_gift=line["is_gift"], discount_amount=line_discount,
                )

            for payment in payments:
                sale.payments.create(method=payment["method"], amount=payment["amount"])

    except ValueError as exc:
        _flash_services_form(request)
        messages.error(request, str(exc))
        return redirect("caisse_services")

    _save_service_cart(request, {})
    messages.success(request, "Vente de services validée avec succès.")
    return redirect("invoice", sale_id=sale.id)


# ---------------------------------------------------------------------------
# Catalogue des prestations (ADMIN)
# ---------------------------------------------------------------------------

@admin_required
def services_list_view(request):
    """Catalogue des prestations de l'entreprise active : ajout, recherche,
    et accès à la modification/suppression."""
    company = get_active_company(request)
    if not company:
        return render(request, "core/services_list.html", {"company": None})

    query = request.GET.get("q", "").strip()
    services = Service.objects.filter(company=company)
    if query:
        services = services.filter(name__icontains=query)

    form = ServiceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        service = form.save(commit=False)
        service.company = company
        service.save()
        messages.success(request, "Prestation ajoutée avec succès.")
        return redirect("services_list")

    return render(request, "core/services_list.html", {
        "company": company, "services": services, "form": form, "query": query,
    })


@admin_required
def service_edit_view(request, service_id):
    service = get_object_or_404(Service, id=service_id)
    form = ServiceForm(request.POST or None, instance=service)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prestation modifiée avec succès.")
        return redirect("services_list")
    return render(request, "core/service_form.html", {"service": service, "form": form})


@admin_required
def service_delete_view(request, service_id):
    """Suppression d'une prestation. Si des ventes y font déjà référence,
    la suppression est bloquée : on propose de la désactiver à la place."""
    service = get_object_or_404(Service, id=service_id)
    if request.method == "POST":
        try:
            service.delete()
            messages.success(request, "Prestation supprimée.")
        except ProtectedError:
            messages.error(
                request,
                f"Impossible de supprimer « {service.name} » : des ventes y font référence. "
                "Décochez plutôt « Prestation active ».",
            )
    return redirect("services_list")


@manager_required
def depenses_list_view(request):
    company = get_active_company(request)
    if not company:
        return render(request, "core/depenses_list.html", {"company": None})

    query = request.GET.get("q", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    depenses = Depense.objects.filter(company=company)
    if query:
        depenses = depenses.filter(Q(type_depense__icontains=query) | Q(label__icontains=query))
    if start_date:
        depenses = depenses.filter(date__gte=start_date)
    if end_date:
        depenses = depenses.filter(date__lte=end_date)

    form = DepenseForm(request.POST or None, initial={"date": timezone.now().date()})
    if request.method == "POST" and "create_depense" in request.POST and form.is_valid():
        depense = form.save(commit=False)
        depense.company = company
        depense.save()
        messages.success(request, "Dépense enregistrée avec succès.")
        return redirect("depenses_list")

    total = sum(d.amount for d in depenses)

    return render(request, "core/depenses_list.html", {
        "company": company, "depenses": depenses, "form": form,
        "query": query, "start_date": start_date or "", "end_date": end_date or "", "total": total,
    })


@admin_required
@manager_required
def depense_delete_view(request, depense_id):
    depense = get_object_or_404(Depense, id=depense_id)
    if request.method == "POST":
        depense.delete()
        messages.success(request, "Dépense supprimée.")
    return redirect("depenses_list")



@admin_required
@manager_required
def product_restock_view(request, product_id):
    """Approvisionnement (réception de stock) d'un produit : incrémente son
    stock et enregistre le mouvement dans l'historique des approvisionnements."""
    product = get_object_or_404(Product, id=product_id)
    form = ApprovisionnementForm(request.POST or None, initial={"date": timezone.now().date()})

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            Approvisionnement.objects.create(
                company=product.company,
                product=product,
                quantity=form.cleaned_data["quantity"],
                unit_cost=form.cleaned_data.get("unit_cost"),
                date=form.cleaned_data["date"],
                comment=form.cleaned_data.get("comment") or None,
            )
            product.stock = F("stock") + form.cleaned_data["quantity"]
            product.save(update_fields=["stock"])
        messages.success(request, f"Stock de « {product.name} » mis à jour (+{form.cleaned_data['quantity']}).")
        return redirect("products_list")

    return render(request, "core/product_restock_form.html", {"product": product, "form": form})


@manager_required
@manager_required
def approvisionnements_list_view(request):
    """Historique des approvisionnements (entrées de stock) de l'entreprise active."""
    company = get_active_company(request)
    if not company:
        return render(request, "core/approvisionnements_list.html", {"company": None})

    entries = Approvisionnement.objects.filter(company=company).select_related("product")

    query = request.GET.get("q", "").strip()
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    if query:
        entries = entries.filter(product__name__icontains=query)
    if start_date:
        entries = entries.filter(date__gte=start_date)
    if end_date:
        entries = entries.filter(date__lte=end_date)

    total_cost = sum((e.unit_cost or 0) * e.quantity for e in entries)

    return render(request, "core/approvisionnements_list.html", {
        "company": company, "entries": entries, "query": query,
        "start_date": start_date or "", "end_date": end_date or "", "total_cost": total_cost,
    })