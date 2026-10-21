# Synchronisation "local -> cloud"
#
# Envoie vers le serveur en ligne les données créées ou modifiées
# depuis la dernière synchronisation réussie.
#
# IMPORTANT :
# - Les comptes User ne sont JAMAIS synchronisés.
# - Aucun mot de passe n'est envoyé.
# - seller_name est conservé dans Sale afin d'identifier le vendeur
#   sans synchroniser son compte.
#
# Données synchronisées :
#   - Company
#   - Employee
#   - Product
#   - Service
#   - Sale
#   - Depense
#   - Approvisionnement
#   - Commande (+ CommandeItem, CommandeAvance, CommandeLivraison)


import base64
import json
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from .models import (
    Approvisionnement,
    Commande,
    CommandeAvance,
    CommandeItem,
    CommandeLivraison,
    Company,
    Depense,
    Employee,
    Product,
    Sale,
    Service,
    SyncState,
)


# ============================================================================
# TYPES DE DONNÉES SYNCHRONISÉS
# ============================================================================

# IMPORTANT :
# "users" n'est volontairement PAS présent ici.
#
# Les comptes User restent locaux à chaque installation.
#
SYNC_KEYS = [
    "companies",
    "employees",
    "products",
    "services",
    "sales",
    "depenses",
    "approvisionnements",
    "commandes",
]


# ============================================================================
# ÉTAT DE SYNCHRONISATION
# ============================================================================

def _get_last_synced(key):
    """
    Retourne la date de la dernière synchronisation réussie
    pour un type de données.
    """

    state, _ = SyncState.objects.get_or_create(key=key)

    return state.last_synced_at


def _set_last_synced(key, when):
    """
    Enregistre la date de la dernière synchronisation réussie.
    """

    SyncState.objects.update_or_create(
        key=key,
        defaults={
            "last_synced_at": when,
        },
    )


def _iso(dt):
    """
    Convertit une date Django en ISO 8601.
    """

    return dt.isoformat() if dt else None


# ============================================================================
# SERIALISATION
# ============================================================================

def _serialize_company(c):
    """
    Entreprise.

    Company possède updated_at :
    les créations et modifications peuvent donc être synchronisées.
    """

    return {
        "id": str(c.id),
        "name": c.name,
        "address": c.address,
        "phone": c.phone,
        "email": c.email,
        "website": c.website,
        "tva_rate": c.tva_rate,
    }


def _serialize_employee(e):
    """
    Employé.

    Employee ne possède pas updated_at.
    On synchronise donc les nouveaux employés avec created_at.
    """

    return {
        "id": str(e.id),
        "company_id": str(e.company_id),
        "full_name": e.full_name,
        "role": e.role,
        "phone": e.phone,
        "is_active": e.is_active,
    }


def _serialize_product(p):
    """
    Produit.

    Product possède updated_at :
    les créations et modifications sont synchronisées.
    """

    return {
        "id": str(p.id),
        "company_id": str(p.company_id),
        "name": p.name,
        "description": p.description,
        "price": p.price,
        "stock": p.stock,
        "critical_threshold": p.critical_threshold,
    }


def _serialize_service(s):
    """
    Prestation.

    Service possède updated_at :
    les créations et modifications sont synchronisées.
    """

    return {
        "id": str(s.id),
        "company_id": str(s.company_id),
        "name": s.name,
        "description": s.description,
        "default_price": s.default_price,
        "is_active": s.is_active,
    }


def _serialize_sale(s):
    """
    Vente.

    Une vente est considérée comme un événement historique.
    Elle possède created_at mais pas updated_at.

    Le compte User du vendeur n'est jamais envoyé.
    Seul seller_name est transmis.
    """

    return {
        # Numéro de la vente sur ce PC (affiché sur la facture).
        "id": str(s.id),
        # Identifiant unique : c'est lui qui permet au serveur de
        # reconnaître la vente, même si un autre PC a le même numéro.
        "sync_uuid": str(s.sync_uuid),
        # Code du poste qui a créé la vente (ex : B1C1).
        "poste_code": s.poste_code,
        "company_id": str(s.company_id),

        "client_name": s.client_name,
        "client_phone": s.client_phone,
        "notes": s.notes,

        "sale_type": s.sale_type,

        "discount_type": s.discount_type,
        "discount_value": s.discount_value,
        "discount_amount": s.discount_amount,

        "sub_total": s.sub_total,
        "tva_amount": s.tva_amount,
        "total": s.total,

        # IMPORTANT :
        # On transmet uniquement le nom du vendeur.
        # Aucun User, mot de passe ou identifiant de connexion.
        "seller_name": s.seller_name,

        "created_at": _iso(s.created_at),

        # --------------------------------------------------------------------
        # ARTICLES DE LA VENTE
        # --------------------------------------------------------------------

        "items": [
            {
                "product_id": (
                    str(item.product_id)
                    if item.product_id
                    else None
                ),

                "service_id": (
                    str(item.service_id)
                    if item.service_id
                    else None
                ),

                "label": item.label,
                "quantity": item.quantity,
                "price": item.price,
                "is_gift": item.is_gift,
                "discount_amount": item.discount_amount,
            }

            for item in s.items.all()
        ],

        # --------------------------------------------------------------------
        # PAIEMENTS
        # --------------------------------------------------------------------

        "payments": [
            {
                "method": payment.method,
                "amount": payment.amount,
            }

            for payment in s.payments.all()
        ],
    }


def _serialize_depense(d):
    """
    Dépense.

    Depense ne possède pas updated_at.
    Une dépense est donc synchronisée avec created_at.
    """

    return {
        "id": str(d.id),
        "company_id": str(d.company_id),

        "date": d.date.isoformat(),

        "type_depense": d.type_depense,
        "label": d.label,

        "amount": d.amount,
        "comment": d.comment,

        "employee_id": (
            str(d.employee_id)
            if d.employee_id
            else None
        ),

        "commande_id": (
            str(d.commande_id)
            if d.commande_id
            else None
        ),
    }


def _serialize_approvisionnement(a):
    """
    Approvisionnement.

    Approvisionnement ne possède pas updated_at.
    Il est donc synchronisé avec created_at.
    """

    return {
        "id": str(a.id),
        "company_id": str(a.company_id),
        "product_id": str(a.product_id),

        "quantity": a.quantity,
        "unit_cost": a.unit_cost,

        "date": a.date.isoformat(),
        "comment": a.comment,
    }


def _serialize_commande(cmd):
    """
    Commande client (paiement échelonné + livraison partielle).

    Commande possède updated_at (mis à jour manuellement à chaque avance
    ou livraison) : les créations ET les modifications sont synchronisées.

    Le compte User du vendeur n'est jamais envoyé, seul seller_name l'est
    (même principe que pour les ventes).
    """

    return {
        "id": str(cmd.id),
        "company_id": str(cmd.company_id),

        "client_name": cmd.client_name,
        "client_phone": cmd.client_phone,
        "notes": cmd.notes,

        "expected_delivery_date": (
            cmd.expected_delivery_date.isoformat() if cmd.expected_delivery_date else None
        ),

        "discount_type": cmd.discount_type,
        "discount_value": cmd.discount_value,
        "discount_amount": cmd.discount_amount,

        "seller_name": cmd.seller_name,

        "created_at": _iso(cmd.created_at),

        "items": [
            {
                "product_id": (
                    str(item.product_id)
                    if item.product_id
                    else None
                ),
                "label": item.label,
                "quantity_ordered": item.quantity_ordered,
                "quantity_delivered": item.quantity_delivered,
                "unit_price": item.unit_price,
                "discount_amount": item.discount_amount,

                "livraisons": [
                    {
                        "quantity": l.quantity,
                        "date": l.date.isoformat(),
                        "comment": l.comment,
                        "created_at": _iso(l.created_at),
                    }
                    for l in item.livraisons.all()
                ],
            }
            for item in cmd.items.all()
        ],

        "avances": [
            {
                "amount": a.amount,
                "method": a.method,
                "date": a.date.isoformat(),
                "comment": a.comment,
                "created_at": _iso(a.created_at),
            }
            for a in cmd.avances.all()
        ],
    }


# ============================================================================
# COLLECTE DES DONNÉES EN ATTENTE
# ============================================================================

def collect_pending_payload():
    """
    Rassemble les données qui doivent être envoyées au cloud.

    Règles :

    Company
        -> created_at + updated_at

    Product
        -> created_at + updated_at

    Service
        -> created_at + updated_at

    Employee
        -> created_at uniquement

    Sale
        -> created_at uniquement

    Depense
        -> created_at uniquement

    Approvisionnement
        -> created_at uniquement

    User
        -> JAMAIS synchronisé.
    """

    payload = {}

    # ========================================================================
    # ENTREPRISES
    # ========================================================================

    since = _get_last_synced("companies")

    qs = Company.objects.all()

    if since:
        qs = qs.filter(
            updated_at__gt=since
        )

    payload["companies"] = [
        _serialize_company(company)
        for company in qs
    ]


    # ========================================================================
    # EMPLOYÉS
    # ========================================================================

    since = _get_last_synced("employees")

    qs = Employee.objects.all()

    if since:
        # Employee possède uniquement created_at.
        qs = qs.filter(
            created_at__gt=since
        )

    payload["employees"] = [
        _serialize_employee(employee)
        for employee in qs
    ]


    # ========================================================================
    # PRODUITS
    # ========================================================================

    since = _get_last_synced("products")

    qs = Product.objects.all()

    if since:
        qs = qs.filter(
            updated_at__gt=since
        )

    payload["products"] = [
        _serialize_product(product)
        for product in qs
    ]


    # ========================================================================
    # PRESTATIONS
    # ========================================================================

    since = _get_last_synced("services")

    qs = Service.objects.all()

    if since:
        qs = qs.filter(
            updated_at__gt=since
        )

    payload["services"] = [
        _serialize_service(service)
        for service in qs
    ]


    # ========================================================================
    # VENTES
    # ========================================================================

    since = _get_last_synced("sales")

    qs = Sale.objects.prefetch_related(
        "items",
        "payments",
    )

    if since:
        # Sale ne possède pas updated_at.
        qs = qs.filter(
            created_at__gt=since
        )

    payload["sales"] = [
        _serialize_sale(sale)
        for sale in qs
    ]


    # ========================================================================
    # DÉPENSES
    # ========================================================================

    since = _get_last_synced("depenses")

    qs = Depense.objects.all()

    if since:
        # Depense ne possède pas updated_at.
        qs = qs.filter(
            created_at__gt=since
        )

    payload["depenses"] = [
        _serialize_depense(depense)
        for depense in qs
    ]


    # ========================================================================
    # APPROVISIONNEMENTS
    # ========================================================================

    since = _get_last_synced("approvisionnements")

    qs = Approvisionnement.objects.all()

    if since:
        # Approvisionnement ne possède pas updated_at.
        qs = qs.filter(
            created_at__gt=since
        )

    payload["approvisionnements"] = [
        _serialize_approvisionnement(approvisionnement)
        for approvisionnement in qs
    ]


    # ========================================================================
    # COMMANDES (paiement échelonné)
    # ========================================================================

    since = _get_last_synced("commandes")

    qs = Commande.objects.prefetch_related("items__livraisons", "avances")

    if since:
        qs = qs.filter(
            updated_at__gt=since
        )

    payload["commandes"] = [
        _serialize_commande(commande)
        for commande in qs
    ]


    return payload


# ============================================================================
# ENVOI VERS LE CLOUD
# ============================================================================

def push_to_cloud():
    """
    Envoie les données en attente vers le serveur cloud, 
    en incluant l'encodage base64 des logos et cachets d'entreprise.

    last_synced_at n'est mis à jour QUE si le serveur cloud
    confirme correctement la réception avec HTTP 200.
    """

    # ========================================================================
    # VÉRIFICATION DE LA CONFIGURATION
    # ========================================================================

    if not settings.CLOUD_SYNC_URL:
        return (
            False,
            "Synchronisation non configurée : "
            "CLOUD_SYNC_URL manquant."
        )

    if not settings.SYNC_TOKEN:
        return (
            False,
            "Synchronisation non configurée : "
            "SYNC_TOKEN manquant."
        )

    if not settings.CLOUD_SYNC_URL.lower().startswith(("https://", "http://")):
        return (
            False,
            "CLOUD_SYNC_URL doit commencer par https:// "
            "(ou http:// en test)."
        )


    # ========================================================================
    # COLLECTE & AJOUT DES IMAGES (LOGO / CACHET) EN BASE64
    # ========================================================================

    # Horodatage pris AVANT la collecte : une donnée créée pendant l'envoi
    # sera reprise à la prochaine synchronisation (aucune perte possible).
    started_at = timezone.now()
    payload = collect_pending_payload()

    # Traitement spécifique pour injecter le logo et le cachet en Base64
    for comp_data in payload.get("companies", []):
        try:
            comp_obj = Company.objects.filter(id=comp_data.get("id")).first()
            if comp_obj:
                if comp_obj.logo and hasattr(comp_obj.logo, "name") and comp_obj.logo.name:
                    try:
                        with comp_obj.logo.open("rb") as f:
                            comp_data["logo_base64"] = base64.b64encode(f.read()).decode("utf-8")
                            comp_data["logo_name"] = os.path.basename(comp_obj.logo.name)
                    except Exception:
                        pass
                if comp_obj.stamp and hasattr(comp_obj.stamp, "name") and comp_obj.stamp.name:
                    try:
                        with comp_obj.stamp.open("rb") as f:
                            comp_data["stamp_base64"] = base64.b64encode(f.read()).decode("utf-8")
                            comp_data["stamp_name"] = os.path.basename(comp_obj.stamp.name)
                    except Exception:
                        pass
        except Exception:
            pass

    total_records = sum(
        len(records)
        for records in payload.values()
    )

    if total_records == 0:
        return (
            True,
            "Rien à synchroniser."
        )


    # ========================================================================
    # CONVERSION JSON
    # ========================================================================

    body = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


    # ========================================================================
    # REQUÊTE HTTP
    # ========================================================================

    request = urllib.request.Request(
        settings.CLOUD_SYNC_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Sync-Token": settings.SYNC_TOKEN,
            # Certains hébergeurs (LiteSpeed/cPanel, dont hostcm) bloquent
            # par défaut le User-Agent générique d'urllib (renvoie un 412
            # Precondition Failed avant même d'atteindre Django).
            "User-Agent": "FacturierSyncClient/1.0",
        },
    )


    # ========================================================================
    # ENVOI
    # ========================================================================

    try:

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:

            if response.status != 200:
                return (
                    False,
                    f"Réponse inattendue du serveur "
                    f"({response.status})."
                )


    except urllib.error.HTTPError as exc:

        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = ""

        return (
            False,
            f"Erreur HTTP du serveur cloud : {exc.code} {exc.reason} — {error_body}"
        )


    except urllib.error.URLError as exc:

        return (
            False,
            "Pas de connexion internet ou serveur "
            f"injoignable : {exc.reason}"
        )


    except TimeoutError:

        return (
            False,
            "Le serveur cloud n'a pas répondu "
            "dans le délai imparti."
        )


    except OSError as exc:

        return (
            False,
            f"Erreur réseau : {exc}"
        )


    # ========================================================================
    # SUCCÈS
    # ========================================================================

    # On ne modifie les SyncState qu'après confirmation
    # du serveur cloud.

    for key in SYNC_KEYS:

        _set_last_synced(
            key,
            started_at
        )


    return (
        True,
        f"{total_records} enregistrement(s) "
        "synchronisé(s)."
    )

