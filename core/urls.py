# Routes de toutes les pages de l'application.

from django.urls import path

from . import views

urlpatterns = [
    # Authentification
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("mot-de-passe-oublie/", views.reset_password_view, name="reset_password"),
    path("changer-entreprise/", views.switch_company_view, name="switch_company"),

    # Dashboard (ADMIN)
    path("", views.dashboard_view, name="dashboard"),

    # Entreprises
    path("entreprises/", views.companies_list_view, name="companies_list"),
    path("entreprises/<uuid:company_id>/", views.company_edit_view, name="company_edit"),
    path("entreprises/<uuid:company_id>/supprimer/", views.company_delete_view, name="company_delete"),

    # Vendeurs
    path("vendeurs/", views.users_list_view, name="users_list"),

    # Produits
    path("produits/", views.products_list_view, name="products_list"),
    path("produits/<uuid:product_id>/modifier/", views.product_edit_view, name="product_edit"),
    path("produits/<uuid:product_id>/supprimer/", views.product_delete_view, name="product_delete"),
    path("produits/importer/", views.product_import_view, name="product_import"),
    path("produits/importer/modele/", views.product_import_template_view, name="product_import_template"),

    # Caisse + session de caisse
    path("caisse/", views.caisse_view, name="caisse"),
    path("caisse/ouverture/", views.cash_session_open_view, name="cash_session_open"),
    path("caisse/prolonger/", views.cash_session_extend_view, name="cash_session_extend"),
    path("caisse/fermer/", views.cash_session_close_view, name="cash_session_close"),

    # Historique
    path("historique/", views.sales_history_view, name="sales_history"),

    # Facture
    path("factures/<int:sale_id>/", views.invoice_view, name="invoice"),
    path("factures/<int:sale_id>/pdf/", views.invoice_pdf_view, name="invoice_pdf"),
]
