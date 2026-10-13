# Plusieurs PC de caisse synchronisés vers un seul serveur en ligne :
# chaque vente reçoit un identifiant unique (sync_uuid), le code du poste
# qui l'a créée (poste_code) et, côté serveur, son numéro d'origine
# (local_number).

import uuid

from django.db import migrations, models

# Les ventes existantes reçoivent un identifiant calculé à partir de leur
# numéro, et non tiré au hasard : le PC et le serveur obtiennent ainsi le
# MÊME identifiant pour une même vente déjà synchronisée, ce qui évite les
# doublons. Cette valeur ne doit jamais changer (elle est aussi utilisée
# dans core/views.py pour les PC pas encore mis à jour).
LEGACY_SALE_NAMESPACE = uuid.UUID("6f1c2b8e-3d4a-4e5b-9c7d-2a1b0c9d8e7f")


def fill_sync_uuid(apps, schema_editor):
    Sale = apps.get_model("core", "Sale")
    for sale in Sale.objects.all().only("id"):
        Sale.objects.filter(pk=sale.pk).update(
            sync_uuid=uuid.uuid5(LEGACY_SALE_NAMESPACE, f"sale-{sale.pk}")
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_depense_updated_at_employee_updated_at"),
    ]

    operations = [
        # 1. Champ ajouté sans contrainte (les ventes existantes restent vides)...
        migrations.AddField(
            model_name="sale",
            name="sync_uuid",
            field=models.UUIDField(null=True, editable=False),
        ),
        # 2. ... rempli vente par vente ...
        migrations.RunPython(fill_sync_uuid, migrations.RunPython.noop),
        # 3. ... puis rendu obligatoire et unique.
        migrations.AlterField(
            model_name="sale",
            name="sync_uuid",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
        migrations.AddField(
            model_name="sale",
            name="poste_code",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
        migrations.AddField(
            model_name="sale",
            name="local_number",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
