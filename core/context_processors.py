# Injecte automatiquement dans le contexte de TOUS les templates :
# - `companies` : la liste des entreprises (pour le sélecteur de la Navbar, ADMIN uniquement)
# - `active_company` : l'entreprise actuellement active (Navbar + pages)
# Évite de dupliquer cette logique dans chaque vue.

from .helpers import get_active_company
from .models import Company, User


def active_company_processor(request):
    if not request.user.is_authenticated:
        return {}

    context = {"active_company": get_active_company(request)}
    if request.user.role == User.Role.ADMIN:
        context["companies"] = Company.objects.order_by("name")
    return context
