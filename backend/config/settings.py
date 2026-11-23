"""Django settings, driven entirely by environment variables.

Nothing environment-specific is hardcoded here: the same image runs in dev, CI and
production, and only the environment differs. See .env.example for the full list.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Only meaningful for local development: `python manage.py runserver` has nothing else
# that puts backend/.env's values into the process. Docker Compose and production both
# inject the environment before the process starts (env_file: / systemd's
# EnvironmentFile), so a missing file here is the normal case for them, not an error —
# and override=False means an already-set variable is never shadowed by a stray file,
# which matters most for production if one were ever accidentally present.
load_dotenv(BASE_DIR / ".env", override=False)


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", False)

# A missing SECRET_KEY must be fatal in production but must not block a fresh clone
# from running tests, so the insecure fallback exists only when DEBUG is on.
SECRET_KEY = env(
    "DJANGO_SECRET_KEY", default="insecure-dev-key" if DEBUG else None, required=not DEBUG
)

# The values a hurried deploy actually reaches for. A key that is *present* passes the
# required check above while being no secret at all, and every session cookie and
# password-reset token in the system rests on it — so the placeholders that ship in this
# repo's own example file are refused outright rather than warned about.
INSECURE_SECRET_KEYS = {"insecure-dev-key", "change-me-in-production", "ci-secret-key", "secret"}
if not DEBUG and SECRET_KEY in INSECURE_SECRET_KEYS:
    raise RuntimeError(
        "DJANGO_SECRET_KEY is set to a known placeholder value. Generate a real one:\n"
        '  python -c "from django.core.management.utils import get_random_secret_key; '
        'print(get_random_secret_key())"'
    )

# A dedicated secret, never a reuse of SECRET_KEY — losing it means every stored
# vault entry becomes permanently undecryptable (no rotation tooling exists for
# this iteration; see docs/designs/work-credential-store.md's Open Questions).
# The DEBUG-only fallback is a fixed, valid-format Fernet key — insecure because
# it is predictable, not because it is malformed, the same distinction
# SECRET_KEY's own "insecure-dev-key" default makes.
VAULT_ENCRYPTION_KEY = env(
    "VAULT_ENCRYPTION_KEY",
    default="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=" if DEBUG else None,
    required=not DEBUG,
)

# A dedicated directory, never STATIC_ROOT or any web-served path — the only way
# to read a file back is the screenshots app's audited `view` action.
SCREENSHOT_STORAGE_ROOT = env(
    "SCREENSHOT_STORAGE_ROOT",
    default=str(BASE_DIR / "screenshot_storage") if DEBUG else None,
    required=not DEBUG,
)
os.makedirs(SCREENSHOT_STORAGE_ROOT, exist_ok=True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    # Local
    "accounts",
    "core",
    "employees",
    "attendance",
    "computers",
    "activities",
    "reports",
    "tasks",
    "vault",
    "events",
    "screenshots",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "office_management"),
        "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", "postgres"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "60")),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # Ten rather than Django's eight. This is a workforce-surveillance system whose
        # admin account can export everyone's movements; two characters is a cheap
        # margin.
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# §30 "password hashing". Stated explicitly rather than left to the default, because
# what the default *is* matters here and a silent change of Django's ordering would be
# invisible. Argon2 first — it is memory-hard, which PBKDF2 is not — with the rest kept
# so existing hashes still verify and are upgraded on next login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# --- Localisation -----------------------------------------------------------

# Storage is always UTC. The office-local timezone used to derive attendance dates
# lives in AppSettings (see PLAN.md A1) and is deliberately NOT this setting.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static -----------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- DRF --------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "2000/hour",
        # Login is throttled far harder than anything else: it is the only endpoint
        # where brute forcing is useful.
        "login": "10/min",
        # Agent scopes are separate from the browser defaults. Registration is
        # unauthenticated and identified by IP, and a whole office can sit behind one
        # NAT address during a rollout, so 60/min anon would be too tight; 30/min is
        # still hopeless odds against a 10-character single-use code. Heartbeats are
        # authenticated per device but counted per employee, who may own several PCs.
        "agent-register": "30/min",
        "agent": "120/min",
        # Decrypting a stored credential is the other action where unlimited
        # attempts are actually useful to an attacker (scripted scraping of every
        # entry a session can reach); the blanket 2000/hour "user" rate was never
        # meant to cover it.
        "vault-reveal": "30/min",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # DRF reads `?format=` during content negotiation and 404s when it names a renderer
    # that is not installed. Only JSONRenderer is installed, so that feature can never
    # do anything but reject a request — and it collides with §26's documented
    # `/api/reports/{type}/export/?format=csv|xlsx`, which is a parameter of ours, not
    # a renderer selector. Turning the override off leaves the parameter to the view.
    "URL_FORMAT_OVERRIDE": None,
}

# --- CORS -------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = True

# --- Security ---------------------------------------------------------------
# §30. The rule throughout: every hardening default is ON, and turning one off takes a
# deliberate environment variable. A deploy that forgets to configure anything is
# secure; it is misconfiguration that has to be explicit, not safety.

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# The CSRF cookie is read by the frontend to echo the token back, so it cannot be
# HttpOnly. That is the documented Django pattern and is not a weakening: the token's
# job is to prove the request came from our page, not to be a secret.
CSRF_COOKIE_HTTPONLY = False
# Unset (None) by default: the frontend and API sharing one origin (or, in dev, sharing
# the literal hostname "localhost" regardless of port — cookies are not port-scoped)
# means the cookie is already visible where it is read.
#
# Only needed — and only correct — when frontend and API are on *different subdomains*
# of the same parent domain (e.g. app.example.com and api.example.com): a cookie with no
# explicit Domain defaults to the exact host that set it, so document.cookie on the
# frontend's own page can never see it, no matter how correctly CORS_ALLOWED_ORIGINS and
# CSRF_TRUSTED_ORIGINS are configured — those govern the request, not what a *different*
# origin's JavaScript is allowed to read back afterwards. The CSRF header ends up empty
# on every authenticated POST/PATCH/DELETE, and DRF's session auth only starts enforcing
# CSRF once a request actually has a session — so login itself works, and the failure
# shows up one request later, looking exactly like a permissions bug. Set this to the
# shared parent with a leading dot (.example.com) to fix it; leave unset for same-origin
# or same-hostname-different-port setups, where setting it would only narrow the
# cookie's default scope for no benefit.
CSRF_COOKIE_DOMAIN = env("DJANGO_CSRF_COOKIE_DOMAIN", None)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Sessions expire rather than living forever. Two weeks is Django's default and far too
# long for a system holding a whole workforce's movements; a working day plus a margin
# means a browser left logged in on a shared machine is not a standing key.
SESSION_COOKIE_AGE = int(env("DJANGO_SESSION_COOKIE_AGE", 12 * 60 * 60))
SESSION_SAVE_EVERY_REQUEST = True

# Always on, not just `if not DEBUG`: without it, Django has no way to know a request
# arrived over HTTPS once it has passed through a reverse proxy (Cloudflare here), and
# treats every request as plain HTTP regardless of what the browser actually used. That
# makes `request.build_absolute_uri()` — DRF's pagination `next`/`previous` links, and
# this project's own `image_url` fields — emit `http://` links that a browser serving
# the page over HTTPS then blocks outright as mixed content. Harmless when DEBUG is on
# and there is no proxy in front (the X-Forwarded-Proto header simply never arrives),
# so there is no dev-mode reason to gate it the way the HTTPS-enforcement settings below
# are.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)

    # HSTS tells the browser never to try this host over HTTP again. That is exactly
    # why it defaults to a year here and why it must not be switched on before HTTPS
    # actually works: a wrong HSTS header is remembered by every visitor's browser and
    # cannot be withdrawn. Set DJANGO_SECURE_HSTS_SECONDS=0 for the first deploy of a
    # host, then raise it once certificates are confirmed good.
    SECURE_HSTS_SECONDS = int(env("DJANGO_SECURE_HSTS_SECONDS", 31_536_000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    # Preload is off by default: submitting to the browsers' preload list is close to
    # irreversible and is an organisational decision, not a deployment default.
    SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)

# `manage.py check --deploy` must come back clean, so the one warning we have decided
# against is silenced here with its reason rather than left to be scrolled past. A
# deploy check that always prints a known warning is a deploy check nobody reads.
#   security.W021 — HSTS preload. See the note above: opting into the browsers' preload
#   list is effectively permanent and belongs to whoever owns the domain, not to this
#   file. Set DJANGO_SECURE_HSTS_PRELOAD=true when that decision has been taken.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- Logging ----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO")},
}
