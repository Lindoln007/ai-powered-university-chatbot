"""
Django settings for the AI Powered University Chatbot backend.

All environment-specific values (secrets, database credentials, thresholds)
are read from environment variables, optionally loaded from a local `.env`
file. See `.env.example` for the full list.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Development-only fallback so the project starts without a .env file.
        SECRET_KEY = "django-insecure-development-only-key-change-me"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",
    # Project apps
    "accounts",
    "knowledge_base",
    "nlp_engine",
    "chat",
    "feedback",
    "analytics",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        # Only used by Django Admin, the browsable API and Swagger UI.
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database (PostgreSQL is the primary source of truth)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "university_chatbot"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Reuse PostgreSQL connections. Opening a new connection costs ~50 ms on Windows, and the
# development server handles every request in a new thread, so a small pool saves that
# time on every API call. Falls back to persistent per-thread connections if disabled.
if env_bool("DB_POOL", True):
    DATABASES["default"]["OPTIONS"] = {
        "pool": {"min_size": 1, "max_size": env_int("DB_POOL_MAX_SIZE", 4), "timeout": 10},
    }
else:
    DATABASES["default"]["CONN_MAX_AGE"] = env_int("DB_CONN_MAX_AGE", 60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Africa/Blantyre")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "university-chatbot",
    }
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("THROTTLE_ANON", "120/minute"),
        "user": os.getenv("THROTTLE_USER", "300/minute"),
        "chat_message": os.getenv("THROTTLE_CHAT_MESSAGE", "30/minute"),
        "auth": os.getenv("THROTTLE_AUTH", "10/minute"),
        "feedback": os.getenv("THROTTLE_FEEDBACK", "30/minute"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Powered University Chatbot API",
    "DESCRIPTION": (
        "REST API for a retrieval-based university FAQ chatbot that uses the "
        "sentence-transformers/all-MiniLM-L6-v2 model for semantic search. "
        "Prototype context: DMI St. John the Baptist University (Malawi). "
        "Records marked as demonstration information are hypothetical and are NOT "
        "official university information."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "UserRoleEnum": "accounts.models.User.Role",
        "RegistrationRoleEnum": [("student", "Student"), ("prospective_student", "Prospective Student")],
    },
}

# ---------------------------------------------------------------------------
# CORS / CSRF (for a separately hosted frontend)
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-csrftoken",
    "x-requested-with",
    "x-guest-token",
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG and env_bool("SECURE_COOKIES", True)
SESSION_COOKIE_SECURE = not DEBUG and env_bool("SECURE_COOKIES", True)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------------------
# NLP engine / chatbot behaviour
# ---------------------------------------------------------------------------
NLP_MODEL_NAME = os.getenv("NLP_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
NLP_MODEL_CACHE_DIR = Path(os.getenv("NLP_MODEL_CACHE_DIR", str(BASE_DIR / "ml_models")))
# When true the model is loaded strictly from the local cache (no network access).
NLP_OFFLINE = env_bool("NLP_OFFLINE", False)
NLP_DEVICE = os.getenv("NLP_DEVICE", "cpu")
# "onnx" (default): the model's official ONNX export on ONNX Runtime; identical embeddings, fast start-up.
# "torch": the sentence-transformers library on PyTorch.
NLP_BACKEND = os.getenv("NLP_BACKEND", "onnx").strip().lower()
NLP_BATCH_SIZE = env_int("NLP_BATCH_SIZE", 32)
# CPU threads used for inference (0 = automatic: physical cores, max 4).
NLP_THREADS = env_int("NLP_THREADS", env_int("NLP_TORCH_THREADS", 0))
# Load the model when the development server starts, so the first question is fast.
NLP_PRELOAD_MODEL = env_bool("NLP_PRELOAD_MODEL", True)
NLP_INTENTS_FILE = Path(os.getenv("NLP_INTENTS_FILE", str(BASE_DIR / "data" / "intents.json")))
NLP_INTENT_THRESHOLD = env_float("NLP_INTENT_THRESHOLD", 0.40)

# Cosine similarity threshold below which no answer is returned (fallback).
CHATBOT_SIMILARITY_THRESHOLD = env_float("CHATBOT_SIMILARITY_THRESHOLD", 0.50)
# If the top two different FAQs are within this margin, ask for clarification...
CHATBOT_CLARIFICATION_MARGIN = env_float("CHATBOT_CLARIFICATION_MARGIN", 0.03)
# ...unless the best score is already at or above this level.
CHATBOT_HIGH_CONFIDENCE = env_float("CHATBOT_HIGH_CONFIDENCE", 0.75)
CHATBOT_MAX_QUESTION_LENGTH = env_int("CHATBOT_MAX_QUESTION_LENGTH", 500)
CHATBOT_TOP_K = env_int("CHATBOT_TOP_K", 5)
# Weight of the previous topic's embedding when resolving short follow-up questions.
CHATBOT_CONTEXT_WEIGHT = env_float("CHATBOT_CONTEXT_WEIGHT", 0.35)
# Demo mode allows clearly labelled hypothetical (unverified) information to be used.
CHATBOT_DEMO_MODE = env_bool("CHATBOT_DEMO_MODE", True)
CHATBOT_INSTITUTION_NAME = os.getenv("CHATBOT_INSTITUTION_NAME", "DMI St. John the Baptist University")
KNOWLEDGE_SEARCH_MIN_SCORE = env_float("KNOWLEDGE_SEARCH_MIN_SCORE", 0.30)
# Regenerate embeddings automatically whenever knowledge records are saved.
KNOWLEDGE_AUTO_EMBED = env_bool("KNOWLEDGE_AUTO_EMBED", True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "sentence_transformers": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "httpx2": {"level": "WARNING"},
        "huggingface_hub": {"level": "ERROR"},
        "transformers": {"level": "ERROR"},
    },
}
