import os
from pathlib import Path
import django
import sentry_sdk
from envparse import env
from djangoeditorwidgets.config import init_web_editor_config
from sentry_sdk.integrations.django import DjangoIntegration


DEBUG = env.bool("DEBUG")
SECRET_KEY = env.str("SECRET_KEY")
BOT_API_KEY = env.str("BOT_API_KEY")
ALLOWED_HOSTS = ["localhost", "crawler.m-gh.com"]
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rangefilter",
    "rest_framework",
    "agency",
    "ai",
    "notification",
    "clear_cache",
    "prettyjson",
    "djangoeditorwidgets",
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

ROOT_URLCONF = "crawler.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "crawler.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASS"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


USE_TZ = True
USE_I18N = True
USE_L10N = True
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tehran"

# CELERY
BROKER_URL = "redis://crawler-redis:6379"
CELERY_RESULT_BACKEND = "redis://crawler-redis:6379"
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Tehran"


STATIC_URL = "/static/"
if DEBUG:
    STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)
else:
    STATIC_ROOT = os.path.join(BASE_DIR, "static")


REST_FRAMEWORK = {
    # When you enable API versioning, the request.version attribute will contain a string
    # that corresponds to the version requested in the incoming client request.
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Email Configs
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST = env("EMAIL_HOST", default="smtp-mail.outlook.com")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default=None)
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default=None)

# Email Logging Configs
ADMIN_EMAIL_LOG = env("ADMIN_EMAIL_LOG", default=None)
ADMINS = (("Log Admin", ADMIN_EMAIL_LOG),)
SERVER_EMAIL = EMAIL_HOST_USER


BASE_DIR_ = Path(__file__).resolve().parent.parent
WEB_EDITOR_DOWNLOAD, WEB_EDITOR_CONFIG = init_web_editor_config(
    # set the directory where files are downloaded
    BASE_DIR_ / "static",
    # set static url prefix
    STATIC_URL,
)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if (dsn := env.str("SENTRY_DSN", default=None)) is not None:
    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=True,
        environment="crawler-prod",
    )


django.setup()  # we need setup django to have access to apps
# Logging (Just Email Handler)
LOG_LEVEL = env("LOG_LEVEL", default="ERROR")

if EMAIL_HOST_USER and ADMIN_EMAIL_LOG:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": "%(asctime)s %(levelname)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",  # Custom date/time format
            }
        },
        "handlers": {
            "mail_admins": {
                "level": "ERROR",
                "class": "reusable.logging.CustomAdminEmailHandler",
                "formatter": "simple",
            },
            "log_db": {
                "class": "reusable.logging.DBHandler",
                "level": "ERROR",
            },
            "log_all_info": {
                "class": "logging.FileHandler",
                "filename": "/app/crawler/logs/all_info.log",
                "mode": "a",
                "level": "INFO",
                "formatter": "simple",
            },
            "log_all_error": {
                "class": "logging.FileHandler",
                "filename": "/app/crawler/logs/all_error.log",
                "mode": "a",
                "level": "ERROR",
                "formatter": "simple",
            },
            "log_celery_info": {
                "class": "logging.FileHandler",
                "filename": "/app/crawler/logs/celery_info.log",
                "mode": "a",
                "level": "INFO",
                "formatter": "simple",
            },
            "log_celery_error": {
                "class": "logging.FileHandler",
                "filename": "/app/crawler/logs/celery_error.log",
                "mode": "a",
                "level": "ERROR",
                "formatter": "simple",
            },
        },
        "loggers": {
            # all modules
            "": {
                "handlers": [
                    "mail_admins",
                    "log_db",
                    "log_all_info",
                    "log_all_error",
                ],
                "level": f"{LOG_LEVEL}",
                "propagate": False,
            },
            # celery modules
            "celery": {
                "handlers": [
                    "mail_admins",
                    "log_db",
                    "log_celery_info",
                    "log_celery_error",
                ],
                "level": f"{LOG_LEVEL}",
                "propagate": False,  # if True, will propagate to root logger
            },
        },
    }


CACHES = {
    "default": {
        "LOCATION": "redis://social_redis:6379",
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
    }
}


# proxy settings
PROXY_HOST = env("PROXY_HOST", default=None)
PROXY_PORT = env("PROXY_PORT", default=None)
PROXY_USER = env("PROXY_USER", default=None)
PROXY_PASS = env("PROXY_PASS", default=None)
