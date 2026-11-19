import os
import re
import sys
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables from .env if present
env_file = BASE_DIR / '.env'
if env_file.is_file():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))

# Execution mode flags
_is_running_tests = 'test' in sys.argv
_is_collectstatic = 'collectstatic' in sys.argv or os.environ.get('DJANGO_COLLECTSTATIC') == '1'

# Environment identifier (e.g. 'development', 'staging', 'production')
ENVIRONMENT = (os.environ.get('ENVIRONMENT') or os.environ.get('RAILWAY_ENVIRONMENT') or '').strip().lower()

# Explicit cloud/production runtime environment detection
_is_cloud_env = bool(
    os.environ.get('RAILWAY_ENVIRONMENT')
    or os.environ.get('RAILWAY_SERVICE_ID')
    or ENVIRONMENT in ('production', 'staging', 'prod')
)

# DJANGO_DEBUG Resolution:
# - If explicitly provided via DJANGO_DEBUG environment variable: strictly respect it.
# - If running on cloud platforms (e.g. Railway) or when no local .env file exists: default safely to False.
# - If running in local development with .env present on disk: default conveniently to True.
if 'DJANGO_DEBUG' in os.environ:
    DEBUG = os.environ.get('DJANGO_DEBUG', '').lower() in ('true', '1', 'yes')
elif _is_cloud_env or not env_file.is_file():
    DEBUG = False
else:
    DEBUG = True

# Optimize test suite runtime using fast MD5 hasher.
# Standard PBKDF2/argon2 hashers remain strictly enforced outside automated test runs.
if _is_running_tests:
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]

# Secret Key Configuration:
# In development (DEBUG=True), test runs, or build-time static collection, falls back safely to development key.
# In production runtime (DEBUG=False), fails closed if DJANGO_SECRET_KEY is missing or the known dev default.
_raw_secret_key = os.environ.get('DJANGO_SECRET_KEY')
_dev_insecure_key = 'django-insecure-nfc-smart-card-platform-luxury-graphite-2026'

if _raw_secret_key and _raw_secret_key != _dev_insecure_key:
    SECRET_KEY = _raw_secret_key
elif DEBUG or _is_running_tests or _is_collectstatic:
    SECRET_KEY = _raw_secret_key or _dev_insecure_key
else:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable must be set in production when DEBUG=False.")

def validate_railway_staging_hostname(hostname: str) -> str:
    """
    Validates that the provided hostname is a single valid DNS hostname ending in .up.railway.app.
    Rejects schemes, ports, paths, wildcards, commas, whitespace, and unresolved placeholders.
    Fails closed with ImproperlyConfigured if invalid or empty.
    """
    if not hostname or not isinstance(hostname, str):
        raise ImproperlyConfigured("RAILWAY_PUBLIC_DOMAIN is missing or empty in staging environment.")
    val = hostname.strip().lower()
    if not val:
        raise ImproperlyConfigured("RAILWAY_PUBLIC_DOMAIN cannot be empty.")
    if '://' in val or val.startswith(('http:', 'https:')):
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must not contain a URL scheme: '{val}'")
    if ':' in val:
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must not contain a port: '{val}'")
    if '/' in val or '\\' in val:
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must not contain path characters: '{val}'")
    if '*' in val:
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must not contain wildcards: '{val}'")
    if ',' in val or ';' in val or ' ' in val:
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must be a single hostname, not a list: '{val}'")
    if ('<' in val and '>' in val) or val.startswith('<') or val.endswith('>'):
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must not be a placeholder: '{val}'")
    if not val.endswith('.up.railway.app'):
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must end with '.up.railway.app': '{val}'")
    dns_pattern = r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*\.up\.railway\.app$'
    if not re.match(dns_pattern, val):
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN is not a valid DNS hostname: '{val}'")
    prefix = val[:-len('.up.railway.app')]
    if not prefix or prefix.endswith('.'):
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN must have a valid subdomain prefix before '.up.railway.app': '{val}'")
    if len(val) > 253:
        raise ImproperlyConfigured(f"RAILWAY_PUBLIC_DOMAIN exceeds maximum DNS hostname length: '{val}'")
    return val


def configure_staging_hostname(environment: str, raw_railway_domain: str) -> tuple:
    """
    Given environment and raw RAILWAY_PUBLIC_DOMAIN, resolves and validates staging host settings:
    Returns (ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, SITE_URL).
    Fails closed with ImproperlyConfigured if hostname is missing, empty, or invalid in staging.
    Never falls back to strideid.com.
    """
    if str(environment).strip().lower() != 'staging':
        raise ImproperlyConfigured("configure_staging_hostname should only be invoked when ENVIRONMENT=staging.")
    valid_host = validate_railway_staging_hostname(raw_railway_domain)
    allowed_hosts = [valid_host, '127.0.0.1', 'localhost']
    csrf_origins = [f"https://{valid_host}"]
    site_url = f"https://{valid_host}"
    return allowed_hosts, csrf_origins, site_url


# ALLOWED_HOSTS & CSRF_TRUSTED_ORIGINS Resolution
# In staging environment on Railway: obtain public hostname dynamically from RAILWAY_PUBLIC_DOMAIN.
# Enforces exact DNS hostname ending in .up.railway.app, rejects wildcards, and fails closed if missing.
# Unresolved values in DJANGO_ALLOWED_HOSTS / DJANGO_CSRF_TRUSTED_ORIGINS cannot override staging hostname.
if ENVIRONMENT == 'staging' and not _is_running_tests and not _is_collectstatic:
    _raw_railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, _staging_site_url = configure_staging_hostname(
        ENVIRONMENT, _raw_railway_domain
    )
else:
    # ALLOWED_HOSTS — always read from environment in production
    # In DEBUG mode, fallback to wildcard for convenience; in production, require explicit hosts
    allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS')
    if allowed_hosts_env:
        ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()]
    elif DEBUG or _is_running_tests or _is_collectstatic:
        ALLOWED_HOSTS = ['*'] if DEBUG else ['127.0.0.1', 'localhost', 'testserver']
    else:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS environment variable must be set in production when DEBUG=False. "
            "Define your trusted production domains (e.g. DJANGO_ALLOWED_HOSTS=.up.railway.app,strideid.com)."
        )

    # CSRF Trusted Origins — read from environment so it works on any domain
    csrf_origins_env = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '')
    if csrf_origins_env:
        CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins_env.split(',') if o.strip()]
    elif DEBUG or _is_running_tests or _is_collectstatic:
        CSRF_TRUSTED_ORIGINS = []
    else:
        raise ImproperlyConfigured(
            "DJANGO_CSRF_TRUSTED_ORIGINS environment variable must be set in production when DEBUG=False. "
            "Define your trusted HTTPS origins (e.g. DJANGO_CSRF_TRUSTED_ORIGINS=https://*.up.railway.app,https://strideid.com)."
        )

# Obscured Admin URL Path (Prevents automated bots and unauthorized visitors from discovering /admin/)
# Set DJANGO_ADMIN_URL in environment if you want a custom secret slug.
ADMIN_URL_PATH = os.environ.get('DJANGO_ADMIN_URL', 'manage-hq-9842').strip('/')

# Cloud reverse proxy (Railway edge) — required so Django knows requests arrive via HTTPS
# Railway terminates SSL and forwards requests as HTTP internally
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security Headers & Browser Protections
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Cookie Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# Production SSL & Secure Cookie Defaults:
# - In development (DEBUG=True) or test runs, defaults safely to False for local HTTP development.
# - In production (DEBUG=False), secure cookies and SSL redirect default to True unless explicitly disabled.
if DEBUG or _is_running_tests or _is_collectstatic:
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1')
    SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
    CSRF_COOKIE_SECURE = os.environ.get('DJANGO_CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1')
else:
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1')
    SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1')
    CSRF_COOKIE_SECURE = os.environ.get('DJANGO_CSRF_COOKIE_SECURE', 'True').lower() in ('true', '1')

# HSTS Configuration:
# Only active when SECURE_HSTS_SECONDS > 0.
# Subdomain and preload directives are disabled by default unless explicitly confirmed.
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '0'))
if SECURE_HSTS_SECONDS > 0:
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() in ('true', '1')
    SECURE_HSTS_PRELOAD = os.environ.get('DJANGO_SECURE_HSTS_PRELOAD', 'False').lower() in ('true', '1')
else:
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Cache Backend (used for shared rate limiting, throttles, and session caching)
# In production runtime (DEBUG=False and not running tests/collectstatic), REDIS_URL is strictly required.
# In development (DEBUG=True) or test runs, REDIS_URL is used if provided,
# otherwise falls back safely to LocMemCache.
REDIS_URL = os.environ.get('REDIS_URL')

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
elif _is_collectstatic:
    # Build-time static collection does not require Redis connectivity
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stride-build-cache',
        }
    }
elif DEBUG or _is_running_tests:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stride-security-cache',
        }
    }
else:
    raise ImproperlyConfigured(
        "REDIS_URL environment variable must be set in production when DEBUG=False. "
        "Production rate limits and security throttles must not run on local memory cache (LocMemCache)."
    )

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sitemaps',

    # Custom Platform Apps
    'apps.accounts.apps.AccountsConfig',
    'apps.core.apps.CoreConfig',
    'apps.profiles.apps.ProfilesConfig',
    'apps.cards.apps.CardsConfig',
    'apps.orders.apps.OrdersConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.websites.apps.WebsitesConfig',
    'apps.analytics.apps.AnalyticsConfig',

    # Cloudinary Persistent Media Storage
    'cloudinary_storage',
    'cloudinary',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves static files efficiently in production.
    # Must be placed directly after SecurityMiddleware and before all others.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # Catches RateLimitServiceUnavailable and renders controlled HTTP 503
    'apps.core.security.RateLimitResilienceMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.brand_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database Configuration:
# - In production runtime (DEBUG=False and not running tests/collectstatic), DATABASE_URL is strictly required.
#   Django will fail closed on startup if DATABASE_URL is missing, preventing accidental SQLite usage in production.
# - In development (DEBUG=True) or during test suite execution, DATABASE_URL is used if provided,
#   otherwise falls back safely to local SQLite3.
# - Connects via standard PostgreSQL driver (psycopg) to any provider (Neon, Railway Postgres, etc.).
# - Auto-detects Neon transaction pooler (-pooler in hostname) and disables server-side cursors to prevent PgBouncer errors.
DATABASE_URL = os.environ.get('DATABASE_URL')
_test_with_db_url = os.environ.get('TEST_WITH_DATABASE_URL', 'False').lower() in ('true', '1')

if DATABASE_URL and (not _is_running_tests or _test_with_db_url):
    _is_neon_pooler = '-pooler' in DATABASE_URL
    _disable_cursors = _is_neon_pooler or os.environ.get('DJANGO_DISABLE_SERVER_SIDE_CURSORS', 'False').lower() in ('true', '1')
    _conn_max_age_default = 60 if _is_neon_pooler else 600
    _conn_max_age = int(os.environ.get('DJANGO_DB_CONN_MAX_AGE', str(_conn_max_age_default)))
    _ssl_require = ('sslmode=require' in DATABASE_URL.lower()) or (not DEBUG and not _is_running_tests)

    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=_conn_max_age,
            conn_health_checks=True,
            disable_server_side_cursors=_disable_cursors,
            ssl_require=_ssl_require,
        )
    }
elif _is_collectstatic:
    # Build-time static collection does not require a database connection
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif DEBUG or _is_running_tests:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable must be set in production when DEBUG=False. "
        "Production environments must not run on SQLite."
    )

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Password Reset Token Timeout (30 minutes)
PASSWORD_RESET_TIMEOUT = 1800

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Cloudinary Persistent Media Storage Configuration
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '').lstrip('@').strip()
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '').strip()
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '').strip()

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET and not _is_running_tests:
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': CLOUDINARY_CLOUD_NAME,
        'API_KEY': CLOUDINARY_API_KEY,
        'API_SECRET': CLOUDINARY_API_SECRET,
    }
    MEDIA_URL = f'https://res.cloudinary.com/{CLOUDINARY_CLOUD_NAME}/'
    default_storage_backend = 'cloudinary_storage.storage.MediaCloudinaryStorage'
elif _is_running_tests or _is_collectstatic or DEBUG:
    MEDIA_URL = '/media/'
    default_storage_backend = 'django.core.files.storage.FileSystemStorage'
else:
    missing_cloudinary = []
    if not CLOUDINARY_CLOUD_NAME:
        missing_cloudinary.append('CLOUDINARY_CLOUD_NAME')
    if not CLOUDINARY_API_KEY:
        missing_cloudinary.append('CLOUDINARY_API_KEY')
    if not CLOUDINARY_API_SECRET:
        missing_cloudinary.append('CLOUDINARY_API_SECRET')
    raise ImproperlyConfigured(
        f"Cloudinary persistent media storage credentials missing in production (DEBUG=False): {', '.join(missing_cloudinary)}. "
        "All three credentials (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET) are required in production. "
        "Silent fallback to ephemeral local container storage is strictly prohibited."
    )

MEDIA_ROOT = BASE_DIR / 'media'

# File Storage Configuration:
# - Media files: Cloudinary persistent cloud CDN or local FileSystemStorage
# - Static files: WhiteNoise CompressedManifestStaticFilesStorage in prod, StaticFilesStorage in debug
if DEBUG:
    STORAGES = {
        'default': {
            'BACKEND': default_storage_backend,
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'default': {
            'BACKEND': default_storage_backend,
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth URLs
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:overview'
LOGOUT_REDIRECT_URL = 'core:home'

# Site Domain URL for absolute links (NFC redirects, email links, vCard, etc.)
if ENVIRONMENT == 'staging' and not _is_running_tests and not _is_collectstatic:
    SITE_URL = _staging_site_url
else:
    SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')

# Brand Customization
BRAND_NAME = os.environ.get('BRAND_NAME', 'STRIDE')
BRAND_TAGLINE = os.environ.get('BRAND_TAGLINE', 'Modern Identity. Seamless Connection.')
BRAND_DOMAIN = os.environ.get('BRAND_DOMAIN', 'strideid.com')
BRAND_SUPPORT_EMAIL = os.environ.get('BRAND_SUPPORT_EMAIL', 'support@strideid.com')
BRAND_SUPPORT_PHONE = os.environ.get('BRAND_SUPPORT_PHONE', '07045003128')
BRAND_SUPPORT_PHONE_INTL = os.environ.get('BRAND_SUPPORT_PHONE_INTL', '+2347045003128')
BRAND_SUPPORT_PHONE_WA = os.environ.get('BRAND_SUPPORT_PHONE_WA', '2347045003128')

# Brevo Transactional Email Configuration
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL') or BRAND_SUPPORT_EMAIL
BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'STRIDE')
STAGING_EMAIL_ALLOWLIST = os.environ.get('STAGING_EMAIL_ALLOWLIST', '').strip()

# Paystack Config
# In automated test suite, default to safe sandbox mock keys (mirrors SQLite/LocMemCache test isolation).
# In runtime (staging/production/development), read directly from environment variables.
if _is_running_tests:
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_TEST_PUBLIC_KEY', 'pk_test_stride_mock_public_key')
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_TEST_SECRET_KEY', 'sk_test_stride_mock_secret_key')
    PAYSTACK_TEST_MODE = True
else:
    PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', '').strip()
    PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '').strip()
    PAYSTACK_TEST_MODE = os.environ.get('PAYSTACK_TEST_MODE', 'True').lower() in ('true', '1')

# ── Structured Logging Configuration (stdout/stderr for 12-factor cloud platforms) ──
LOG_LEVEL = os.environ.get('DJANGO_LOG_LEVEL', 'INFO').upper()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': sys.stdout,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING' if not DEBUG else 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        # Application and domain loggers
        'apps': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'uzyra': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'uzyra.payments': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'uzyra.orders': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'uzyra.analytics': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'uzyra.security': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.payments': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.orders': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.analytics': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.security': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.auth': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.email_service': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'stride.cards': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
    },
}
