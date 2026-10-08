import os
import secrets
import string

from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = (
        "Crée le compte administrateur initial. Le mot de passe vient de la variable "
        "SEED_ADMIN_PASSWORD, sinon un mot de passe aléatoire est généré et affiché UNE fois."
    )

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="0000000000", help="Téléphone (10 chiffres) de l'admin")
        parser.add_argument("--name", default="Administrateur Principal")

    def handle(self, *args, **options):
        phone = options["phone"]
        if User.objects.filter(role=User.Role.ADMIN).exists():
            self.stdout.write("Un compte administrateur existe déjà : rien à faire.")
            return

        password = os.getenv("SEED_ADMIN_PASSWORD", "")
        generated = not password
        if generated:
            alphabet = string.ascii_letters + string.digits
            password = "".join(secrets.choice(alphabet) for _ in range(16)) + "#9a"

        User.objects.create_user(
            phone_number=phone, full_name=options["name"], password=password, role=User.Role.ADMIN,
        )
        self.stdout.write(self.style.SUCCESS(f"Compte administrateur créé : téléphone={phone}"))
        if generated:
            self.stdout.write(self.style.WARNING(
                f"Mot de passe généré (notez-le, il ne sera plus affiché) : {password}"
            ))
        self.stdout.write("Changez ce mot de passe dès la première connexion.")
