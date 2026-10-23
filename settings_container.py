"""
Container / CI settings for mediplus.

Imports everything from the project's settings.py and overrides only what
must differ when running in Docker / Kubernetes. settings.py is untouched.
Selected with:  DJANGO_SETTINGS_MODULE=mediplus.settings_container
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403
from .settings import BASE_DIR, MIDDLEWARE

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# SECRET_KEY must come from the environment (K8s Secret / Jenkins), never git.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable is required")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# settings.py has a typo in the CommonPasswordValidator path ("3assword_validation");
# override with the correct list so password validation works in the container.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# SQLite lives on a writable path (emptyDir / volume in Kubernetes).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "data" / "db.sqlite3")),
    }
}

# Static files are collected at image build time and served by WhiteNoise.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media"))

if not DEBUG:
    SESSION_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_CONTENT_TYPE_NOSNIFF = True
