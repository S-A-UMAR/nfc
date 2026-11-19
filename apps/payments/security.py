import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger('stride.payments')


def validate_paystack_credentials(
    public_key: str = None,
    secret_key: str = None,
    test_mode: bool = None,
    environment: str = None,
) -> None:
    """
    Fail-closed safety guard for Paystack credentials.
    Enforces environment isolation and prevents live credentials from being used
    in staging or test environments.

    Rules:
    1. In staging (ENVIRONMENT=staging):
       - Reject live credentials (starts with 'sk_live_' or 'pk_live_').
       - Reject missing credentials (empty or unconfigured).
       - Reject invalid test credentials (must start with 'pk_test_' and 'sk_test_').
       - Enforce PAYSTACK_TEST_MODE=True.
    2. When PAYSTACK_TEST_MODE=True (any environment):
       - Reject live credentials (starts with 'sk_live_' or 'pk_live_').
    3. Consistency:
       - Reject mismatched credential types (e.g. pk_test_ with sk_live_ or pk_live_ with sk_test_).
    4. Credential Protection:
       - Never print, log, or leak actual secret or public keys in messages or exceptions.
    """
    if public_key is None:
        public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
    if secret_key is None:
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if test_mode is None:
        test_mode = getattr(settings, 'PAYSTACK_TEST_MODE', True)
    if environment is None:
        environment = getattr(settings, 'ENVIRONMENT', '')

    pub = (public_key or '').strip()
    sec = (secret_key or '').strip()
    is_test_mode = bool(test_mode)
    env = (environment or '').strip().lower()

    pub_is_live = pub.startswith('pk_live_')
    pub_is_test = pub.startswith('pk_test_')
    sec_is_live = sec.startswith('sk_live_')
    sec_is_test = sec.startswith('sk_test_')

    # Rule 1: Staging Environment Isolation Guard
    if env == 'staging':
        if not pub or not sec:
            raise ImproperlyConfigured(
                "Paystack credentials missing in staging environment. "
                "Both PAYSTACK_PUBLIC_KEY and PAYSTACK_SECRET_KEY must be configured with test keys."
            )

        if pub_is_live or sec_is_live:
            raise ImproperlyConfigured(
                "Live Paystack credentials are strictly prohibited in the staging environment. "
                "Use sandbox test keys (pk_test_... / sk_test_...)."
            )

        if not pub_is_test or not sec_is_test:
            raise ImproperlyConfigured(
                "Invalid Paystack credentials for staging environment. "
                "PAYSTACK_PUBLIC_KEY must start with 'pk_test_' and PAYSTACK_SECRET_KEY must start with 'sk_test_'."
            )

        if not is_test_mode:
            raise ImproperlyConfigured(
                "PAYSTACK_TEST_MODE must be True in the staging environment."
            )

    # Rule 2: Test Mode Live Credential Guard
    if is_test_mode:
        if pub_is_live or sec_is_live:
            raise ImproperlyConfigured(
                "Live Paystack credentials cannot be used when PAYSTACK_TEST_MODE is True."
            )

    # Rule 3: Consistency Guard (Reject Mismatched Key Types)
    if (pub_is_test and sec_is_live) or (pub_is_live and sec_is_test):
        raise ImproperlyConfigured(
            "Paystack credential mismatch: PAYSTACK_PUBLIC_KEY and PAYSTACK_SECRET_KEY "
            "must both be test keys or both be live keys."
        )
