import os
import threading

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Facturier - Cœur métier"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return

        from django.conf import settings

        def sync_loop():
            import time
            from core.sync_client import push_to_cloud
            while True:
                try:
                    push_to_cloud()
                except Exception:
                    pass  # pas de connexion : on réessaiera au prochain cycle
                time.sleep(settings.SYNC_INTERVAL_MINUTES * 60)

        if getattr(settings, "CLOUD_SYNC_URL", ""):
            threading.Thread(target=sync_loop, daemon=True).start()