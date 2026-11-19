from django.test import TestCase, Client
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.payments.security import validate_paystack_credentials

User = get_user_model()


class PaystackSafetyGuardUnitTests(TestCase):
    """
    Focused unit verification for the Paystack staging and test-mode safety guard.
    Validates fail-closed behavior across environments, credential types, and configurations.
    """

    def test_staging_with_valid_test_keys(self):
        """Staging environment with valid test keys passes validation."""
        # Should not raise
        validate_paystack_credentials(
            public_key="pk_test_sample_public_key_12345",
            secret_key="sk_test_sample_secret_key_67890",
            test_mode=True,
            environment="staging"
        )

    def test_staging_with_live_secret_key(self):
        """Staging environment rejects live secret key with ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="pk_test_sample_public_key_12345",
                secret_key="sk_live_compromised_production_secret",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Live Paystack credentials are strictly prohibited in the staging environment", str(ctx.exception))
        self.assertNotIn("sk_live_compromised_production_secret", str(ctx.exception))

    def test_staging_with_live_public_key(self):
        """Staging environment rejects live public key with ImproperlyConfigured."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="pk_live_compromised_production_public",
                secret_key="sk_test_sample_secret_key_67890",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Live Paystack credentials are strictly prohibited in the staging environment", str(ctx.exception))
        self.assertNotIn("pk_live_compromised_production_public", str(ctx.exception))

    def test_staging_with_both_live_keys(self):
        """Staging environment rejects when both public and secret keys are live."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="pk_live_sample_public_key",
                secret_key="sk_live_sample_secret_key",
                test_mode=False,
                environment="staging"
            )
        self.assertIn("Live Paystack credentials are strictly prohibited in the staging environment", str(ctx.exception))

    def test_staging_with_missing_credentials(self):
        """Staging environment fails closed if either or both credentials are empty or missing."""
        # Missing both
        with self.assertRaises(ImproperlyConfigured) as ctx1:
            validate_paystack_credentials(
                public_key="",
                secret_key="",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Paystack credentials missing in staging environment", str(ctx1.exception))

        # Missing secret key only
        with self.assertRaises(ImproperlyConfigured) as ctx2:
            validate_paystack_credentials(
                public_key="pk_test_sample_public_key",
                secret_key="",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Paystack credentials missing in staging environment", str(ctx2.exception))

        # Missing public key only
        with self.assertRaises(ImproperlyConfigured) as ctx3:
            validate_paystack_credentials(
                public_key="",
                secret_key="sk_test_sample_secret_key",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Paystack credentials missing in staging environment", str(ctx3.exception))

        # Missing in settings when called without arguments
        with self.settings(ENVIRONMENT='staging', PAYSTACK_PUBLIC_KEY='', PAYSTACK_SECRET_KEY=''):
            with self.assertRaises(ImproperlyConfigured) as ctx4:
                validate_paystack_credentials()
            self.assertIn("Paystack credentials missing in staging environment", str(ctx4.exception))

    def test_staging_with_invalid_test_credentials(self):
        """Staging environment rejects keys that do not start with pk_test_ and sk_test_."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="invalid_pk_format_12345",
                secret_key="invalid_sk_format_67890",
                test_mode=True,
                environment="staging"
            )
        self.assertIn("Invalid Paystack credentials for staging environment", str(ctx.exception))

    def test_staging_with_test_mode_disabled(self):
        """Staging environment requires PAYSTACK_TEST_MODE to be True."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="pk_test_sample_public_key",
                secret_key="sk_test_sample_secret_key",
                test_mode=False,
                environment="staging"
            )
        self.assertIn("PAYSTACK_TEST_MODE must be True in the staging environment", str(ctx.exception))

    def test_staging_with_mismatched_credential_types(self):
        """Staging rejects mismatched key combinations."""
        # test public with live secret
        with self.assertRaises(ImproperlyConfigured):
            validate_paystack_credentials(
                public_key="pk_test_sample",
                secret_key="sk_live_sample",
                test_mode=True,
                environment="staging"
            )

        # live public with test secret
        with self.assertRaises(ImproperlyConfigured):
            validate_paystack_credentials(
                public_key="pk_live_sample",
                secret_key="sk_test_sample",
                test_mode=True,
                environment="staging"
            )

    def test_test_mode_with_live_credentials(self):
        """Regardless of environment, PAYSTACK_TEST_MODE=True rejects any live credentials."""
        # Live secret in test mode (e.g. in development or default env)
        with self.assertRaises(ImproperlyConfigured) as ctx1:
            validate_paystack_credentials(
                public_key="pk_test_sample_key",
                secret_key="sk_live_secret_key",
                test_mode=True,
                environment="development"
            )
        self.assertIn("Live Paystack credentials cannot be used when PAYSTACK_TEST_MODE is True", str(ctx1.exception))

        # Live public in test mode
        with self.assertRaises(ImproperlyConfigured) as ctx2:
            validate_paystack_credentials(
                public_key="pk_live_sample_key",
                secret_key="sk_test_secret_key",
                test_mode=True,
                environment=""
            )
        self.assertIn("Live Paystack credentials cannot be used when PAYSTACK_TEST_MODE is True", str(ctx2.exception))

        # Both live in test mode
        with self.assertRaises(ImproperlyConfigured) as ctx3:
            validate_paystack_credentials(
                public_key="pk_live_sample_key",
                secret_key="sk_live_secret_key",
                test_mode=True,
                environment=""
            )
        self.assertIn("Live Paystack credentials cannot be used when PAYSTACK_TEST_MODE is True", str(ctx3.exception))

    def test_production_with_legitimate_live_credentials(self):
        """Production environment with legitimate live credentials and test_mode=False passes cleanly."""
        validate_paystack_credentials(
            public_key="pk_live_real_paystack_public_key",
            secret_key="sk_live_real_paystack_secret_key",
            test_mode=False,
            environment="production"
        )

    def test_production_with_mismatched_credential_types(self):
        """Production rejects mismatched credentials (e.g. pk_test_ with sk_live_)."""
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key="pk_test_sandbox_public",
                secret_key="sk_live_real_secret",
                test_mode=False,
                environment="production"
            )
        self.assertIn("Paystack credential mismatch", str(ctx.exception))

    def test_local_development_without_credentials(self):
        """Local development without configured keys passes (does not block non-payment development)."""
        validate_paystack_credentials(
            public_key="",
            secret_key="",
            test_mode=True,
            environment=""
        )

    def test_credentials_never_leaked_in_exceptions(self):
        """Exception messages must never leak the actual sensitive key strings."""
        sensitive_secret = "sk_live_super_secret_unreleased_token_9999"
        sensitive_public = "pk_live_super_secret_public_token_8888"

        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_paystack_credentials(
                public_key=sensitive_public,
                secret_key=sensitive_secret,
                test_mode=True,
                environment="staging"
            )
        err_msg = str(ctx.exception)
        self.assertNotIn(sensitive_secret, err_msg)
        self.assertNotIn(sensitive_public, err_msg)
        self.assertNotIn("9999", err_msg)
        self.assertNotIn("8888", err_msg)


class PaystackSafetyGuardViewIntegrationTests(TestCase):
    """
    View-level verification that payment requests fail closed before execution
    if credentials violate safety rules.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='shopper@strideid.com',
            password='Password123!',
            first_name='Shopper',
            last_name='User'
        )
        self.package = ProductPackage.objects.create(
            code='standard-nfc-safety',
            name='Standard NFC Card Safety',
            package_type='card_only',
            price_ngn=15000,
            is_active=True
        )
        self.order = Order.objects.create(
            user=self.user,
            package=self.package,
            amount=15000,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            reference="STR-SAFETY-REF-001",
            amount=15000,
            provider='paystack',
            status=Payment.STATUS_PENDING,
        )

    def test_initialize_payment_view_fails_closed_in_staging_with_live_key(self):
        """initialize_payment_view raises ImproperlyConfigured in staging when live keys are configured."""
        self.client.force_login(self.user)
        url = reverse('payments:initialize', kwargs={'order_number': self.order.order_number})

        with self.settings(
            ENVIRONMENT='staging',
            PAYSTACK_PUBLIC_KEY='pk_live_compromised_key',
            PAYSTACK_SECRET_KEY='sk_test_valid_key',
            PAYSTACK_TEST_MODE=True
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.get(url)

    def test_verify_payment_view_fails_closed_when_test_mode_has_live_secret(self):
        """verify_payment_view raises ImproperlyConfigured before making any Paystack API request."""
        self.client.force_login(self.user)
        url = reverse('payments:verify')

        with self.settings(
            PAYSTACK_TEST_MODE=True,
            PAYSTACK_PUBLIC_KEY='pk_test_sample',
            PAYSTACK_SECRET_KEY='sk_live_illegal_in_test_mode',
            ENVIRONMENT='staging'
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.get(f"{url}?reference={self.payment.reference}")

    def test_paystack_webhook_fails_closed_when_test_mode_has_live_secret(self):
        """paystack_webhook_view raises ImproperlyConfigured before checking signature."""
        url = reverse('payments:webhook')
        payload = '{"event": "charge.success", "data": {"reference": "STR-SAFETY-REF-001"}}'

        with self.settings(
            PAYSTACK_TEST_MODE=True,
            PAYSTACK_PUBLIC_KEY='pk_test_sample',
            PAYSTACK_SECRET_KEY='sk_live_illegal_in_test_mode',
            ENVIRONMENT='staging'
        ):
            with self.assertRaises(ImproperlyConfigured):
                self.client.post(url, data=payload, content_type='application/json')

    def test_initialize_payment_view_succeeds_with_valid_staging_keys(self):
        """initialize_payment_view renders successfully with valid staging test keys."""
        self.client.force_login(self.user)
        url = reverse('payments:initialize', kwargs={'order_number': self.order.order_number})

        with self.settings(
            ENVIRONMENT='staging',
            PAYSTACK_PUBLIC_KEY='pk_test_valid_sandbox_public_key',
            PAYSTACK_SECRET_KEY='sk_test_valid_sandbox_secret_key',
            PAYSTACK_TEST_MODE=True
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'pk_test_valid_sandbox_public_key')
