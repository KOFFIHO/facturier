# Détermine l'entreprise "active" pour la requête en cours :
# - un SELLER est toujours rattaché à SA propre entreprise ;
# - un ADMIN choisit une entreprise active via un sélecteur dans la Navbar,
#   mémorisé en session (voir views.switch_company_view).

from .models import Company, User


def get_active_company(request):
    """Retourne l'entreprise active pour l'utilisateur connecté, ou None si
    aucune entreprise n'est disponible/sélectionnée."""
    user = request.user
    if not user.is_authenticated:
        return None

    if user.role == User.Role.SELLER:
        return user.company

    # ADMIN : entreprise mémorisée en session, sinon la première disponible
    company_id = request.session.get("active_company_id")
    if company_id:
        company = Company.objects.filter(id=company_id).first()
        if company:
            return company

    first_company = Company.objects.order_by("name").first()
    if first_company:
        request.session["active_company_id"] = str(first_company.id)
    return first_company
