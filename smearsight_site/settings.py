"""Django settings for SmearSight (single-computer, offline use)."""
import os
from pathlib import Path

from django.db.backends.signals import connection_created

from core.services.config import BASE_DIR, DATA_DIR, DB_PATH, STATIC_DIR

SECRET_KEY = os.environ.get("SMEARSIGHT_SECRET", "smearsight-local-only-change-me-if-exposed")
DEBUG = os.environ.get("SMEARSIGHT_DEBUG", "") == "1"
ALLOWED_HOSTS = ["*"]            # the app is meant for one lab computer / local Wi-Fi

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.PinGateMiddleware",
]

ROOT_URLCONF = "smearsight_site.urls"
WSGI_APPLICATION = "smearsight_site.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages"]},
}]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DB_PATH,
                         "OPTIONS": {"timeout": 30}}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("SMEARSIGHT_TZ", "Africa/Kampala")
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [STATIC_DIR]
STATIC_ROOT = DATA_DIR / "collected_static"      # only used by /admin/ assets
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],         # access is controlled by the optional PIN gate
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer",
                                 "rest_framework.renderers.BrowsableAPIRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser", "rest_framework.parsers.MultiPartParser",
                               "rest_framework.parsers.FormParser"],
    "EXCEPTION_HANDLER": "core.views.api_exception_handler",
    "UNAUTHENTICATED_USER": None,
}


def _sqlite_pragmas(sender, connection, **kw):
    if connection.vendor == "sqlite":
        cur = connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=30000;")


connection_created.connect(_sqlite_pragmas)
