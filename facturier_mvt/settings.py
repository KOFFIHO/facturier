# Configuration du projet Django - Facturier Automatique (SQLite + templates).
# Version durcie pour la production (hébergement mutualisé / cPanel sans SSH).
#
# Toute la configuration sensible passe par le fichier .env (jamais versionné).

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_list(name, default=""):
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


# --- Mode debug : FALSE par défaut (production) ---
DEBUG = _env_bool("DEBUG", False)

# --- Clé secrète : obligatoire en production, aucune valeur de secours ---
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY manquant dans le fichier .env (obligatoire quand DEBUG=False)."
        )
elif not DEBUG and (len(SECRET_KEY) < 40 or SECRET_KEY.startswith("changez-moi")):
    raise ImproperlyConfigured(
        "SECRET_KEY trop faible : générez une clé aléatoire d'au moins 50 caractères."
    )

# --- Domaines autorisés : à renseigner dans .env (ALLOWED_HOSTS=monsite.com,www.monsite.com) ---
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS manquant dans .env (ex. ALLOWED_HOSTS=www.doumbia.shop,doumbia.shop)."
    )

CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "facturier_mvt.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.active_company_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "facturier_mvt.wsgi.application"

# --- Base de données : SQLite ---
# DB_PATH permet de placer la base HORS du dossier public (recommandé).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("DB_PATH") or (BASE_DIR / "db.sqlite3"),
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_USER_MODEL = "core.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques (CSS, JS) ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "core" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Fichiers uploadés (logo, cachet) : servis par une vue protégée (login requis) ---
MEDIA_URL = "/uploads/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT") or (BASE_DIR / "uploads"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification ---
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "caisse"
LOGOUT_REDIRECT_URL = "login"

# --- Limites d'upload ---
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 Mo (logo, cachet, import Excel)
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # inclut les lots de synchronisation
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# --- Cache sur fichiers (partagé entre les processus Passenger, sert à l'anti force brute) ---
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(Path(os.getenv("CACHE_DIR") or (BASE_DIR / "cache"))),
    }
}

# --- Protection anti force brute (connexion) ---
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

# --- Sessions et cookies ---
SESSION_COOKIE_AGE = 60 * 60 * 12          # 12 h
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# --- En-têtes de sécurité ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    # Mettre FORCE_HTTPS=False dans .env UNIQUEMENT si le site n'a pas encore de certificat SSL.
    FORCE_HTTPS = _env_bool("FORCE_HTTPS", True)
    if FORCE_HTTPS:
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = int(os.getenv("HSTS_SECONDS", "31536000"))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = False
        SECURE_HSTS_PRELOAD = False
        # Derrière le proxy Passenger/Apache de l'hébergeur
        if _env_bool("BEHIND_PROXY", True):
            SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Journalisation : fichier, jamais d'erreur technique affichée au visiteur ---
LOG_DIR = Path(os.getenv("LOG_DIR") or (BASE_DIR / "logs"))
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _handlers = {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "app.log"),
            "maxBytes": 1_000_000,
            "backupCount": 3,
            "encoding": "utf-8",
        }
    }
    _handler_names = ["file"]
except OSError:
    _handlers = {"null": {"class": "logging.NullHandler"}}
    _handler_names = ["null"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": _handlers,
    "loggers": {
        "django": {"handlers": _handler_names, "level": "WARNING", "propagate": False},
        "core": {"handlers": _handler_names, "level": "INFO", "propagate": False},
    },
}

# --- Synchronisation vers un serveur en ligne (cloud) ---
CLOUD_SYNC_URL = os.getenv("CLOUD_SYNC_URL", "")
SYNC_TOKEN = os.getenv("SYNC_TOKEN", "")
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "5"))
# Le serveur cloud n'accepte la réception que si ce réglage est activé (désactivé par défaut)
SYNC_RECEIVE_ENABLED = _env_bool("SYNC_RECEIVE_ENABLED", False)
