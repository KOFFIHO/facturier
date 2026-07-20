# Routes racine du projet : toutes les pages de l'application sont dans
# core.urls ; /admin/ reste l'admin Django natif (utile en développement) ;
# /uploads/ sert les fichiers médias (logo, cachet) en développement.

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
