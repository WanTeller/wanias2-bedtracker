"""
Django settings for the Ward Board project.

Anything sensitive (secret key, database password, email password) is read from
the environment. For local development you can put those in a file called
`.env` in the project root - it is git-ignored and loaded automatically below.
Nothing secret is hard-coded here.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RUNNING_TESTS = "test" in sys.argv

# Speed up the test suite (weak hashing is fine for throwaway test data only).
if RUNNING_TESTS:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


# --------------------------------------------------------------------------- #
# Tiny .env loader (no dependency). Lines like  KEY=value  become os.environ.
# --------------------------------------------------------------------------- #
def _load_dotenv(path):
    try:
        # utf-8-sig tolerates a byte-order mark, which Notepad and some
        # PowerShell commands add when saving the file.
        with open(path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip().lstrip("﻿")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = os.environ.get(
    "BEDTRACKER_SECRET_KEY",
    "django-insecure-dev-only-key-change-me-in-production",
)

DEBUG = _env_bool("BEDTRACKER_DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("BEDTRACKER_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Hosts that Railway / Render inject automatically - so you don't have to set
# BEDTRACKER_ALLOWED_HOSTS by hand on those platforms.
for _auto in (
    os.environ.get("RAILWAY_PUBLIC_DOMAIN", ""),
    os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""),
):
    if _auto and _auto not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_auto)

# Origins allowed to POST (Django requires this once you're on a real domain).
# https:// for every specific non-local ALLOWED_HOST, plus anything in
# BEDTRACKER_CSRF_TRUSTED_ORIGINS (comma-separated, scheme included).
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}"
    for h in ALLOWED_HOSTS
    if h not in ("localhost", "127.0.0.1", "*") and "*" not in h
] + [
    o.strip()
    for o in os.environ.get("BEDTRACKER_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Password for the developer-only "Clear all patient data" control (sidebar).
DEV_CLEAR_PASSWORD = os.environ.get("BEDTRACKER_DEV_CLEAR_PASSWORD", "clear-ward")

# TESTING MODE. When true, the login page asks only for a name (no email /
# password / signup) and drops you straight into the board. The real
# email+password system stays in the code and comes back when this is false.
# See accounts/README-simple-login note in CLAUDE.md.
SIMPLE_LOGIN = os.environ.get("BEDTRACKER_SIMPLE_LOGIN", "false").lower() in (
    "1", "true", "yes", "on",
)
# The test suite controls this per-test with @override_settings, so ignore any
# .env value while running tests (keeps `python manage.py test` deterministic).
if RUNNING_TESTS:
    SIMPLE_LOGIN = False


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "accounts",   # login / signup / user + login registry
    "board",      # the ward board itself
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files straight from the app (no separate CDN /
    # webserver needed on the free host).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Django 5.1: every view needs a logged-in user unless marked
    # @login_not_required. This is our whole access-control layer.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------- #
# Database - resolved in this order:
#   1. DATABASE_URL          (what Neon / most hosts hand you)
#   2. BEDTRACKER_DB=postgres + BEDTRACKER_DB_* (explicit parts)
#   3. local SQLite          (development default)
# Production (DEBUG false) must not fall through to SQLite.
# --------------------------------------------------------------------------- #
import dj_database_url  # noqa: E402

_database_url = os.environ.get("DATABASE_URL", "")

if _database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _database_url, conn_max_age=60, ssl_require=True
        )
    }
elif os.environ.get("BEDTRACKER_DB", "sqlite").lower() == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["BEDTRACKER_DB_NAME"],
            "USER": os.environ["BEDTRACKER_DB_USER"],
            "PASSWORD": os.environ["BEDTRACKER_DB_PASSWORD"],
            "HOST": os.environ.get("BEDTRACKER_DB_HOST", "localhost"),
            "PORT": os.environ.get("BEDTRACKER_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"sslmode": os.environ.get("BEDTRACKER_DB_SSLMODE", "require")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # Override with BEDTRACKER_SQLITE_PATH to point at a restored copy
            # when test-restoring a backup.
            "NAME": os.environ.get(
                "BEDTRACKER_SQLITE_PATH", str(BASE_DIR / "db.sqlite3")
            ),
            "OPTIONS": {
                "timeout": 20,  # wait up to 20s for a write lock instead of erroring
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    "PRAGMA synchronous=NORMAL;"
                    "PRAGMA foreign_keys=ON;"
                ),
            },
        }
    }

# Managed hosts must use PostgreSQL (their disk is wiped on redeploy). When you
# self-host on your own always-on PC, SQLite is fine - opt in explicitly.
if (
    not DEBUG
    and not RUNNING_TESTS
    and "sqlite" in DATABASES["default"]["ENGINE"]
    and not _env_bool("BEDTRACKER_ALLOW_SQLITE", False)
):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "Production (BEDTRACKER_DEBUG=false) defaults to PostgreSQL - set "
        "DATABASE_URL (or BEDTRACKER_DB=postgres + BEDTRACKER_DB_*). If you are "
        "self-hosting on your own machine and want to keep SQLite, set "
        "BEDTRACKER_ALLOW_SQLITE=true."
    )


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Log in with an email address (accounts.auth_backends.EmailBackend), falling
# back to the standard backend so /admin/ superuser logins keep working.
AUTHENTICATION_BACKENDS = [
    "accounts.auth_backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Password-reset emails: printed to the console in development. To turn on real
# emails later, set BEDTRACKER_EMAIL_* (e.g. a free Gmail app password).
if os.environ.get("BEDTRACKER_EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["BEDTRACKER_EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("BEDTRACKER_EMAIL_PORT", "587"))
    EMAIL_USE_TLS = _env_bool("BEDTRACKER_EMAIL_TLS", True)
    EMAIL_HOST_USER = os.environ.get("BEDTRACKER_EMAIL_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("BEDTRACKER_EMAIL_PASSWORD", "")
    DEFAULT_FROM_EMAIL = os.environ.get("BEDTRACKER_EMAIL_FROM", EMAIL_HOST_USER)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# --------------------------------------------------------------------------- #
# i18n / static
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"   # `collectstatic` writes here on the host

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashed filenames + gzip; WhiteNoise serves them with long cache headers.
    # Tests use the plain backend so they don't require `collectstatic` first.
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if RUNNING_TESTS
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Production security (only active when BEDTRACKER_DEBUG=false)
# The free hosts terminate HTTPS at a proxy and forward this header.
# --------------------------------------------------------------------------- #
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = _env_bool("BEDTRACKER_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("BEDTRACKER_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --------------------------------------------------------------------------- #
# Logging - everything to stderr, which the host captures.
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("BEDTRACKER_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
