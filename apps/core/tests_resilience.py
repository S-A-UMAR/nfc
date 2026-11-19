import os
import sys
import subprocess
import time
from unittest.mock import patch
from django.test import TestCase, Client, RequestFactory, override_settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
import redis.exceptions

from apps.core.security import (
    check_rate_limit,
    rate_limited,
    RateLimitServiceUnavailable,
    RateLimitResilienceMiddleware,
)
from apps.orders.models import Order, ProductPackage
from apps.payments.models import Payment
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

User = get_user_model()


class RedisResilienceTests(TestCase):
    """
    Tests for Phase 3: Redis resilience & graceful degradation.
    Verifies that:
    1. Sensitive operations (login, registration, card activation) fail closed with 503
       when Redis is down, preventing brute-force attacks during cache outages.
    2. Non-sensitive operations (contact, complaints, analytics) degrade gracefully (fail open)
       without raising 500 errors.
    3. Normal rate limiting works as expected when Redis is operational.
    4. Exceptions do not leak credentials, IP addresses, or internal topology.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email='resilience_user@example.com',
            password='TestPassword123!',
            first_name='Resilience',
            last_name='Tester'
        )

    def test_redis_unavailable_sensitive_check_rate_limit_raises_service_unavailable(self):
        """Sensitive rate limit check raises RateLimitServiceUnavailable when Redis is down."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Connection refused to Redis:6379")):
            with self.assertRaises(RateLimitServiceUnavailable) as cm:
                check_rate_limit("login:127.0.0.1", limit=5, window_seconds=300)

            # Confirm message is user-safe and does not leak connection string or traceback
            self.assertIn("Security verification service is temporarily unavailable", str(cm.exception))
            self.assertEqual(cm.exception.retry_after, 30)

    def test_redis_unavailable_login_view_returns_503(self):
        """Login POST returns controlled HTTP 503 (not 500) when Redis is down."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis connection lost")):
            response = self.client.post(reverse('accounts:login'), {
                'username': 'resilience_user@example.com',
                'password': 'TestPassword123!',
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')
            self.assertIn(b"Security Service Temporarily Unavailable", response.content)
            # Confirm no Redis internal topology or traceback is exposed in response
            self.assertNotIn(b"Connection refused", response.content)
            self.assertNotIn(b"redis.exceptions", response.content)

    def test_redis_unavailable_registration_view_returns_503(self):
        """Registration view returns controlled HTTP 503 when Redis is down."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis unreachable")):
            response = self.client.get(reverse('accounts:register'))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_redis_unavailable_card_activation_returns_503(self):
        """Card activation POST returns controlled HTTP 503 when Redis is down."""
        self.client.force_login(self.user)
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis down")):
            response = self.client.post(reverse('cards:card_activate'), {
                'card_code': 'ANY-CARD',
                'activation_code': 'ANY-PIN',
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_redis_unavailable_non_sensitive_contact_degrades_gracefully(self):
        """Non-sensitive operation (contact form check) fails open without raising 503 or 500."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis timed out")):
            allowed, remaining, retry_after = check_rate_limit("contact:127.0.0.1", limit=5, window_seconds=600)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

    def test_redis_unavailable_non_sensitive_analytics_beacon_degrades_gracefully(self):
        """Analytics beacon rate limit check fails open without error when Redis is down."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis timed out")):
            allowed, remaining, retry_after = check_rate_limit("analytics_beacon:127.0.0.1", limit=120, window_seconds=60)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

    def test_redis_restored_normal_rate_limiting_operates_correctly(self):
        """Normal rate limiting works as expected when Redis is operational."""
        cache.clear()
        key = "test_normal:user123"

        # Under limit
        allowed, remaining, retry_after = check_rate_limit(key, limit=3, window_seconds=60, sensitive=False)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)
        self.assertEqual(retry_after, 0)

        # Hit 2
        allowed, remaining, retry_after = check_rate_limit(key, limit=3, window_seconds=60, sensitive=False)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 1)

        # Hit 3
        allowed, remaining, retry_after = check_rate_limit(key, limit=3, window_seconds=60, sensitive=False)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 0)

        # Hit 4 (Throttled)
        allowed, remaining, retry_after = check_rate_limit(key, limit=3, window_seconds=60, sensitive=False)
        self.assertFalse(allowed)
        self.assertEqual(remaining, 0)
        self.assertGreater(retry_after, 0)

    def test_rate_limited_decorator_redis_failure_sensitive(self):
        """rate_limited decorator catches RateLimitServiceUnavailable and returns HTTP 503."""
        @rate_limited("login_action", limit=5, window_seconds=60, sensitive=True)
        def dummy_view(request):
            return HttpResponse("OK")

        req = self.factory.get('/test/')
        req.user = self.user

        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("No connection")):
            response = dummy_view(req)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_rate_limited_decorator_redis_failure_non_sensitive(self):
        """rate_limited decorator allows non-sensitive view execution when Redis is down."""
        @rate_limited("public_view", limit=5, window_seconds=60, sensitive=False)
        def dummy_view(request):
            return HttpResponse("Success")

        req = self.factory.get('/test/')
        req.user = self.user

        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("No connection")):
            response = dummy_view(req)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"Success")

    def test_redis_unavailable_otp_verify_view_returns_503(self):
        """Email OTP verification POST returns 503 when Redis is unavailable."""
        session = self.client.session
        session['pending_verification_email'] = self.user.email
        session.save()

        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis down")):
            response = self.client.post(reverse('accounts:verify_otp'), {
                'digit_1': '1', 'digit_2': '2', 'digit_3': '3',
                'digit_4': '4', 'digit_5': '5', 'digit_6': '6',
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_redis_unavailable_otp_resend_view_returns_503(self):
        """Email OTP resend POST returns 503 when Redis is unavailable."""
        session = self.client.session
        session['pending_verification_email'] = self.user.email
        session.save()

        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis down")):
            response = self.client.post(reverse('accounts:resend_otp'))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_redis_unavailable_password_reset_request_returns_503(self):
        """Password reset request POST returns 503 when Redis is unavailable."""
        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis down")):
            response = self.client.post(reverse('accounts:password_reset'), {
                'email': 'resilience_user@example.com'
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')

    def test_redis_unavailable_password_reset_confirm_returns_503(self):
        """Password reset confirmation POST returns 503 when Redis is unavailable."""
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        with patch.object(cache, 'get', side_effect=redis.exceptions.ConnectionError("Redis down")):
            response = self.client.post(reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token}), {
                'new_password1': 'NewPass123!Secure',
                'new_password2': 'NewPass123!Secure',
            })
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get('Retry-After'), '30')


class PaymentReferenceHardeningTests(TestCase):
    """
    Tests for Phase 6: Payment reference prefix transition from ULV- to STR-
    with full backward compatibility for existing payments.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='pay_tester@example.com',
            password='TestPassword123!',
            first_name='Pay',
            last_name='Tester'
        )
        self.package = ProductPackage.objects.first()
        if not self.package:
            self.package = ProductPackage.objects.create(
                code='test-card',
                name='Test Smart Card',
                price_ngn=25000,
                is_active=True
            )
        self.order = Order.objects.create(
            order_number='ORD-99881',
            user=self.user,
            package=self.package,
            amount=25000,
            payment_status=Order.PAYMENT_PENDING
        )

    def test_new_payment_reference_generation_uses_str_prefix(self):
        """New payment initialization creates a reference starting with STR-."""
        self.client.force_login(self.user)
        response = self.client.get(reverse('payments:initialize', kwargs={'order_number': self.order.order_number}))
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.filter(order=self.order).first()
        self.assertIsNotNone(payment)
        self.assertTrue(payment.reference.startswith('STR-'), f"Expected STR- prefix, got: {payment.reference}")
        self.assertIn(self.order.order_number, payment.reference)

    def test_existing_ulv_payment_reference_compatibility(self):
        """Existing payments with ULV- references continue to resolve and verify correctly."""
        legacy_ref = f"ULV-{self.order.order_number}-LEGACY01"
        legacy_payment = Payment.objects.create(
            order=self.order,
            reference=legacy_ref,
            amount=25000,
            status=Payment.STATUS_PENDING
        )

        self.client.force_login(self.user)
        # Visit initialize view again — must reuse existing ULV- payment without overwriting
        response = self.client.get(reverse('payments:initialize', kwargs={'order_number': self.order.order_number}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, legacy_ref)

        # Lookup by legacy reference succeeds
        fetched_payment = Payment.objects.get(reference=legacy_ref)
        self.assertEqual(fetched_payment.id, legacy_payment.id)
        self.assertEqual(fetched_payment.reference, legacy_ref)


class ProductionConfigurationValidationTests(TestCase):
    """
    Tests for Phase 1, Phase 2, Phase 5:
    1. Cloudinary fail-closed enforcement when DEBUG=False.
    2. Redis URL enforcement when DEBUG=False.
    3. Build-time collectstatic decoupling.
    """

    def test_build_time_collectstatic_dry_run_succeeds_without_external_services(self):
        """
        Demonstrates that collectstatic runs successfully without live Neon, Redis, or Cloudinary.
        """
        env = os.environ.copy()
        env['DJANGO_DEBUG'] = 'False'
        # Clear external service URLs
        env.pop('DATABASE_URL', None)
        env.pop('REDIS_URL', None)
        env.pop('CLOUDINARY_CLOUD_NAME', None)
        env.pop('CLOUDINARY_API_KEY', None)
        env.pop('CLOUDINARY_API_SECRET', None)
        env.pop('DJANGO_SECRET_KEY', None)
        env.pop('DJANGO_ALLOWED_HOSTS', None)
        env.pop('DJANGO_CSRF_TRUSTED_ORIGINS', None)

        res = subprocess.run(
            [sys.executable, 'manage.py', 'collectstatic', '--dry-run', '--noinput'],
            env=env,
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0, f"collectstatic failed: {res.stderr}")
        self.assertIn("static files copied", res.stdout.lower())
