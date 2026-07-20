from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Crée un compte administrateur par défaut."

    def handle(self, *args, **options):
        admin_phone = "0000000000"
        if not User.objects.filter(phone_number=admin_phone).exists():
            User.objects.create_user(
                phone_number=admin_phone,
                full_name="Administrateur Principal",
                password="Admin@1234",
                role=User.Role.ADMIN,
            )
            self.stdout.write(self.style.SUCCESS(
                "Compte administrateur créé : téléphone=0000000000 / mot de passe=Admin@1234"
            ))
        else:
            self.stdout.write("Un compte administrateur existe déjà.")
