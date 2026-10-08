# Routes racine du projet : toutes les pages de l'application sont dans
# core.urls (y compris /uploads/, servi par une vue protégée par connexion).
# L'URL de l'admin Django est configurable via ADMIN_URL dans .env.

import os

from django.contrib import admin
from django.urls import include, path

_admin_url = os.getenv("ADMIN_URL", "admin/").strip().lstrip("/")
if _admin_url and not _admin_url.endswith("/"):
    _admin_url += "/"

urlpatterns = [
    path(_admin_url or "admin/", admin.site.urls),
    path("", include("core.urls")),
]

handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
handler403 = "core.views.error_403"
