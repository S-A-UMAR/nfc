import os
from pathlib import Path

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

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-nfc-smart-card-platform-luxury-graphite-2026')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS')
if allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['*'] if DEBUG else ['uzyra.com', 'www.uzyra.com', '127.0.0.1', 'localhost', 'testserver']

# ⚠️  TEMPORARY — NFC testing via Cloudflare Tunnel — REMOVE AFTER TESTING
CSRF_TRUSTED_ORIGINS = [
    'https://deal-computing-sent-bias.trycloudflare.com',
]

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

# Production SSL toggles (configurable via environment variables)
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1')
SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1')
CSRF_COOKIE_SECURE = os.environ.get('DJANGO_CSRF_COOKIE_SECURE', 'False').lower() in ('true', '1')
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '0'))
if SECURE_HSTS_SECONDS > 0:
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True').lower() in ('true', '1')
    SECURE_HSTS_PRELOAD = os.environ.get('DJANGO_SECURE_HSTS_PRELOAD', 'True').lower() in ('true', '1')
else:
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Cache Backend (used for rate limiting and sliding session throttle)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'uzyra-security-cache',
    }
}

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Custom Platform Apps
    'apps.accounts.apps.AccountsConfig',
    'apps.core.apps.CoreConfig',
    'apps.profiles.apps.ProfilesConfig',
    'apps.cards.apps.CardsConfig',
    'apps.orders.apps.OrdersConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.websites.apps.WebsitesConfig',
    'apps.analytics.apps.AnalyticsConfig',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

# Media files (User uploads, QR codes, logos)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth URLs
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:overview'
LOGOUT_REDIRECT_URL = 'core:home'

# Site Domain URL for absolute links
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')

# Brand Customization
BRAND_NAME = os.environ.get('BRAND_NAME', 'UZYRA')
BRAND_TAGLINE = 'YOUR IDENTITY. YOUR BUSINESS. ONE TOUCH.'
BRAND_SUPPORT_EMAIL = 'contact@uzyra.com'
BRAND_SUPPORT_PHONE = '+234 800 000 0000'

# Brevo Transactional Email Configuration
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', 'contact@uzyra.com')
BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'UZYRA')

# Paystack Config
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', 'pk_test_sample_public_key')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', 'sk_test_sample_secret_key')
PAYSTACK_TEST_MODE = os.environ.get('PAYSTACK_TEST_MODE', 'True').lower() in ('true', '1')

