"""
Django settings for the operations portal demo.

Local configuration comes from environment variables (see README). Generated
files (database, secret key) live in PORTAL_DATA_DIR (default ./data), which
is git-ignored.
"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PORTAL_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _secret_key() -> str:
    from_env = os.environ.get("PORTAL_SECRET_KEY")
    if from_env:
        return from_env
    key_file = DATA_DIR / "secret_key.txt"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(50)
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key


SECRET_KEY = _secret_key()

DEBUG = os.environ.get("PORTAL_DEBUG", "0") == "1"

ALLOWED_HOSTS = [h for h in os.environ.get("PORTAL_ALLOWED_HOSTS", "*").split(",") if h]

# PORTAL_PUBLIC_ORIGIN is the https origin browsers use when the app sits behind a
# TLS-terminating proxy (e.g. https://8000--<session>.preview.devinapps.com). It is
# added to the CSRF trusted origins and switches the session/CSRF cookies to Secure.
# PORTAL_HTTPS_PROXY=1 does the same for a proxy whose public origin is not known in
# advance (same-origin posts pass Django's Origin check via X-Forwarded-Proto).
#
# The Devin preview proxy rewrites the browser's Origin header to the upstream
# address ("http://localhost"), which Django would otherwise reject with
# "Origin checking failed". PORTAL_PROXY_ORIGINS lists the rewritten origins to
# accept in proxy mode. CSRF protection stays on: the per-session token is still
# required and any other origin is still refused.
PUBLIC_ORIGIN = os.environ.get("PORTAL_PUBLIC_ORIGIN", "").rstrip("/")
BEHIND_HTTPS_PROXY = PUBLIC_ORIGIN.startswith("https://") or os.environ.get("PORTAL_HTTPS_PROXY") == "1"
PROXY_ORIGINS = [
    o for o in os.environ.get("PORTAL_PROXY_ORIGINS", "http://localhost,http://127.0.0.1").split(",") if o
]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("PORTAL_CSRF_TRUSTED_ORIGINS", "").split(",") if o]
for _origin in ([PUBLIC_ORIGIN] if PUBLIC_ORIGIN else []) + (PROXY_ORIGINS if BEHIND_HTTPS_PROXY else []):
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "refunds",
    "kyc",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.roles.role_context",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "portal.sqlite3",
        # Tests always run against a separate in-memory database.
        "TEST": {"NAME": None},
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = DATA_DIR / "staticfiles"
# Serve app static files directly from the source tree (no collectstatic step for the demo).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "refunds:list"
LOGOUT_REDIRECT_URL = "login"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = BEHIND_HTTPS_PROXY
CSRF_COOKIE_SECURE = BEHIND_HTTPS_PROXY
SESSION_COOKIE_SAMESITE = "None" if BEHIND_HTTPS_PROXY else "Lax"
CSRF_COOKIE_SAMESITE = "None" if BEHIND_HTTPS_PROXY else "Lax"
X_FRAME_OPTIONS = "DENY"
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
