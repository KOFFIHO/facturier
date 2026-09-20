# Décorateurs de contrôle d'accès - équivalent des permissions DRF de la
# version API, adaptés aux vues Django classiques (redirection + message).

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import User


def admin_required(view_func):
    """Autorise uniquement les utilisateurs connectés ayant le rôle ADMIN."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            messages.error(request, "Accès réservé à l'administrateur.")
            return redirect("caisse")
        return view_func(request, *args, **kwargs)

    return wrapper


def seller_required(view_func):
    """Autorise uniquement les utilisateurs connectés ayant le rôle SELLER."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != User.Role.SELLER:
            messages.error(request, "Accès réservé aux vendeurs.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper

def manager_required(view_func):
    """Autorise les utilisateurs connectés ayant le rôle ADMIN ou SELLER
    (« Gérant ») — accès élargi à la Caisse, aux Produits et aux Dépenses,
    tout en laissant Entreprises/Vendeurs/Historique/Dashboard à l'ADMIN seul."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in (User.Role.ADMIN, User.Role.SELLER):
            messages.error(request, "Accès non autorisé.")
            return redirect("caisse")
        return view_func(request, *args, **kwargs)

    return wrapper
