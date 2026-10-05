# Routes de toutes les pages de l'application.

from django.urls import path
from django.views.generic import RedirectView

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
    path("vendeurs/", views.users_list_view, name="users_list"),
    path("vendeurs/<uuid:user_id>/supprimer/", views.user_delete_view, name="user_delete"),
    path("vendeurs/<uuid:user_id>/desactiver/", views.user_deactivate_view, name="user_deactivate"),

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

    # Caisse SERVICES + catalogue de prestations
    path("caisse/services/", views.caisse_services_view, name="caisse_services"),
    path("prestations/", views.services_list_view, name="services_list"),
    path("prestations/<uuid:service_id>/modifier/", views.service_edit_view, name="service_edit"),
    path("prestations/<uuid:service_id>/supprimer/", views.service_delete_view, name="service_delete"),

    path("depenses/", views.depenses_list_view, name="depenses_list"),
    path("depenses/<uuid:depense_id>/supprimer/", views.depense_delete_view, name="depense_delete"),

    path("caisse/", views.caisse_view, name="caisse"),
    path("caisse/services/", RedirectView.as_view(pattern_name="caisse"), name="caisse_services"),

    path("produits/<uuid:product_id>/approvisionner/", views.product_restock_view, name="product_restock"),
    path("approvisionnements/", views.approvisionnements_list_view, name="approvisionnements_list"),

    # Synchronisation 
    path("api/sync/receive/", views.sync_receive_view, name="sync_receive"),
    path("synchronisation/", views.sync_status_view, name="sync_status"),
    
    #Employers
    path("employes/", views.employees_list_view, name="employees_list"),
    path("employes/<uuid:employee_id>/desactiver/", views.employee_deactivate_view, name="employee_deactivate"),
]
