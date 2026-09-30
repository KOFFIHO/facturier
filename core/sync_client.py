# Synchronisation "local -> cloud" : envoie les données créées/modifiées
# depuis la dernière synchronisation réussie vers le serveur en ligne
# (accessible au propriétaire), dès qu'une connexion internet est
# disponible. Ne synchronise JAMAIS de mots de passe ni de comptes
# utilisateurs — uniquement les données d'activité.

import json
import urllib.request
import urllib.error

from django.conf import settings
from django.utils import timezone

from .models import Approvisionnement, Company, Depense, Product, Sale, Service, SyncState

SYNC_KEYS = ["companies", "products", "services", "sales", "depenses", "approvisionnements"]


def _get_last_synced(key):
    state, _ = SyncState.objects.get_or_create(key=key)
    return state.last_synced_at


def _set_last_synced(key, when):
    SyncState.objects.update_or_create(key=key, defaults={"last_synced_at": when})


def _iso(dt):
    return dt.isoformat() if dt else None


def _serialize_company(c):
    return {
        "id": str(c.id), "name": c.name, "address": c.address, "phone": c.phone,
        "email": c.email, "website": c.website, "tva_rate": c.tva_rate,
    }


def _serialize_product(p):
    return {
        "id": str(p.id), "company_id": str(p.company_id), "name": p.name,
        "description": p.description, "price": p.price, "stock": p.stock,
        "critical_threshold": p.critical_threshold,
    }


def _serialize_service(s):
    return {
        "id": str(s.id), "company_id": str(s.company_id), "name": s.name,
        "description": s.description, "default_price": s.default_price,
        "is_active": s.is_active,
    }


def _serialize_sale(s):
    return {
        "id": s.id, "company_id": str(s.company_id),
        "client_name": s.client_name, "client_phone": s.client_phone, "notes": s.notes,
        "sale_type": s.sale_type,
        "discount_type": s.discount_type, "discount_value": s.discount_value,
        "discount_amount": s.discount_amount,
        "sub_total": s.sub_total, "tva_amount": s.tva_amount, "total": s.total,
        "seller_name": s.seller_name,
        "created_at": _iso(s.created_at),
        "items": [
            {
                "product_id": str(i.product_id) if i.product_id else None,
                "service_id": str(i.service_id) if i.service_id else None,
                "label": i.label, "quantity": i.quantity, "price": i.price,
                "is_gift": i.is_gift, "discount_amount": i.discount_amount,
            }
            for i in s.items.all()
        ],
        "payments": [{"method": p.method, "amount": p.amount} for p in s.payments.all()],
    }


def _serialize_depense(d):
    return {
        "id": str(d.id), "company_id": str(d.company_id), "date": d.date.isoformat(),
        "type_depense": d.type_depense, "label": d.label, "amount": d.amount,
        "comment": d.comment,
    }


def _serialize_approvisionnement(a):
    return {
        "id": str(a.id), "company_id": str(a.company_id), "product_id": str(a.product_id),
        "quantity": a.quantity, "unit_cost": a.unit_cost, "date": a.date.isoformat(),
        "comment": a.comment,
    }


def collect_pending_payload():
    """Rassemble uniquement les enregistrements créés/modifiés depuis la
    dernière synchronisation réussie de chaque type."""
    payload = {}

    since = _get_last_synced("companies")
    qs = Company.objects.all()
    if since:
        qs = qs.filter(updated_at__gt=since)
    payload["companies"] = [_serialize_company(c) for c in qs]

    since = _get_last_synced("products")
    qs = Product.objects.all()
    if since:
        qs = qs.filter(updated_at__gt=since)
    payload["products"] = [_serialize_product(p) for p in qs]

    since = _get_last_synced("services")
    qs = Service.objects.all()
    if since:
        qs = qs.filter(updated_at__gt=since)
    payload["services"] = [_serialize_service(s) for s in qs]

    since = _get_last_synced("sales")
    qs = Sale.objects.prefetch_related("items", "payments")
    if since:
        qs = qs.filter(created_at__gt=since)
    payload["sales"] = [_serialize_sale(s) for s in qs]

    since = _get_last_synced("depenses")
    qs = Depense.objects.all()
    if since:
        qs = qs.filter(created_at__gt=since)
    payload["depenses"] = [_serialize_depense(d) for d in qs]

    since = _get_last_synced("approvisionnements")
    qs = Approvisionnement.objects.all()
    if since:
        qs = qs.filter(created_at__gt=since)
    payload["approvisionnements"] = [_serialize_approvisionnement(a) for a in qs]

    return payload


def push_to_cloud():
    """Envoie les données en attente vers le serveur en ligne. Ne lève
    jamais d'exception vers l'appelant : une absence de connexion internet
    doit simplement reporter la tentative au prochain cycle."""
    if not settings.CLOUD_SYNC_URL or not settings.SYNC_TOKEN:
        return False, "Synchronisation non configurée (CLOUD_SYNC_URL / SYNC_TOKEN manquants)."

    payload = collect_pending_payload()
    total_records = sum(len(v) for v in payload.values())
    if total_records == 0:
        return True, "Rien à synchroniser."

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        settings.CLOUD_SYNC_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Sync-Token": settings.SYNC_TOKEN},
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                return False, f"Réponse inattendue du serveur ({response.status})."
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"Pas de connexion internet ou serveur injoignable : {exc}"

    now = timezone.now()
    for key in SYNC_KEYS:
        _set_last_synced(key, now)

    return True, f"{total_records} enregistrement(s) synchronisé(s)."