import hmac
import hashlib
import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.cards.models import Card

User = get_user_model()


class Phase3PaymentAndWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.secret_key = "sk_test_mock_paystack_secret_key"

        # Override Paystack settings for test predictability
        self.settings_override = self.settings(
            PAYSTACK_SECRET_KEY=self.secret_key,
            PAYSTACK_PUBLIC_KEY="pk_test_mock_paystack_public_key",
            PAYSTACK_TEST_MODE=True
        )
        self.settings_override.enable()

        # User A
        self.user_a = User.objects.create_user(
            email='user.a@example.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )

        # User B (for IDOR tests)
        self.user_b = User.objects.create_user(
            email='user.b@example.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )

        # Product package
        self.package = ProductPackage.objects.create(
            code='standard-nfc',
            name='Standard NFC Card',
            package_type='card_only',
            price_ngn=15000,
            is_active=True
        )

        # Order for User A
        self.order_a = Order.objects.create(
            user=self.user_a,
            package=self.package,
            amount=15000,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED,
            shipping_name='User A',
            shipping_phone='08012345678',
            shipping_address='123 Tech Street, Lagos'
        )

        # Pending Payment for Order A
        self.payment_ref = f"ULV-{self.order_a.order_number}-TEST01"
        self.payment = Payment.objects.create(
            order=self.order_a,
            reference=self.payment_ref,
            amount=15000,
            provider='paystack',
            status=Payment.STATUS_PENDING
        )

    def tearDown(self):
        self.settings_override.disable()

    def _generate_signature(self, payload_str):
        return hmac.new(
            self.secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

    def test_payment_retry_deduplication(self):
        """Visiting initialize_payment_view multiple times reuses the existing pending payment reference."""
        self.client.force_login(self.user_a)
        url = reverse('payments:initialize', args=[self.order_a.order_number])

        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, 200)

        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, 200)

        # Ensure no duplicate Payment models were created for this order
        pending_payments = Payment.objects.filter(order=self.order_a, status=Payment.STATUS_PENDING)
        self.assertEqual(pending_payments.count(), 1)
        self.assertEqual(pending_payments.first().reference, self.payment_ref)

    def test_forged_webhook_signature_rejected(self):
        """Test B: Forged webhook signature returns 400 Bad Request and does not modify order."""
        url = reverse('payments:webhook')
        payload = {
            "event": "charge.success",
            "data": {
                "reference": self.payment_ref,
                "amount": 1500000, # 15,000 NGN in kobo
                "currency": "NGN",
                "status": "success",
                "channel": "card"
            }
        }
        payload_bytes = json.dumps(payload)

        # Send with invalid signature
        response = self.client.post(
            url,
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='invalid_forged_signature_12345'
        )

        self.assertEqual(response.status_code, 400)
        self.order_a.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order_a.payment_status, Order.PAYMENT_PENDING)
        self.assertEqual(self.payment.status, Payment.STATUS_PENDING)

    def test_webhook_duplicate_event_delivery_idempotent(self):
        """Test A: Duplicate webhook event delivery updates state once and remains idempotent."""
        url = reverse('payments:webhook')
        payload = {
            "event": "charge.success",
            "data": {
                "reference": self.payment_ref,
                "amount": 1500000, # 15,000 NGN in kobo
                "currency": "NGN",
                "status": "success",
                "channel": "card"
            }
        }
        payload_str = json.dumps(payload)
        signature = self._generate_signature(payload_str)

        # First webhook delivery
        resp1 = self.client.post(
            url,
            data=payload_str,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        self.assertEqual(resp1.status_code, 200)

        self.order_a.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)
        self.assertEqual(self.order_a.payment_status, Order.PAYMENT_PAID)

        # Second webhook delivery (duplicate)
        resp2 = self.client.post(
            url,
            data=payload_str,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        self.assertEqual(resp2.status_code, 200)

        # State remains unchanged
        self.order_a.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)
        self.assertEqual(self.order_a.payment_status, Order.PAYMENT_PAID)

    def test_webhook_amount_mismatch_fails_payment(self):
        """Test C: Webhook amount mismatch marks payment as failed and does not pay order."""
        url = reverse('payments:webhook')
        payload = {
            "event": "charge.success",
            "data": {
                "reference": self.payment_ref,
                "amount": 500000, # 5,000 NGN (expected 15,000 NGN)
                "currency": "NGN",
                "status": "success",
                "channel": "card"
            }
        }
        payload_str = json.dumps(payload)
        signature = self._generate_signature(payload_str)

        response = self.client.post(
            url,
            data=payload_str,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order_a.refresh_from_db()

        self.assertEqual(self.payment.status, Payment.STATUS_FAILED)
        self.assertEqual(self.order_a.payment_status, Order.PAYMENT_PENDING)

    def test_webhook_nonexistent_reference_handled_gracefully(self):
        """Test D: Webhook with non-existent reference returns 200 without crashing."""
        url = reverse('payments:webhook')
        payload = {
            "event": "charge.success",
            "data": {
                "reference": "NONEXISTENT-REF-999999",
                "amount": 1500000,
                "currency": "NGN",
                "status": "success",
                "channel": "card"
            }
        }
        payload_str = json.dumps(payload)
        signature = self._generate_signature(payload_str)

        response = self.client.post(
            url,
            data=payload_str,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        self.assertEqual(response.status_code, 200)

    def test_webhook_arrives_before_redirect(self):
        """Test E & F: Webhook arrives before user redirect -> order marked paid, redirect handled cleanly."""
        # 1. Webhook arrives
        url_webhook = reverse('payments:webhook')
        payload = {
            "event": "charge.success",
            "data": {
                "reference": self.payment_ref,
                "amount": 1500000,
                "currency": "NGN",
                "status": "success"
            }
        }
        payload_str = json.dumps(payload)
        signature = self._generate_signature(payload_str)

        self.client.post(
            url_webhook,
            data=payload_str,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )

        # 2. User then visits initialize_payment_view -> redirected because order is already paid
        self.client.force_login(self.user_a)
        url_init = reverse('payments:initialize', args=[self.order_a.order_number])
        resp_init = self.client.get(url_init)

        self.assertEqual(resp_init.status_code, 302)
        self.assertIn(f"/dashboard/orders/{self.order_a.order_number}/", resp_init.url)

    def test_idor_order_access_prevented(self):
        """Test G & H: User B cannot initialize payment or view User A's order."""
        self.client.force_login(self.user_b)

        # User B trying to initialize payment on User A's order -> 404
        url_init = reverse('payments:initialize', args=[self.order_a.order_number])
        resp_init = self.client.get(url_init)
        self.assertEqual(resp_init.status_code, 404)

        # User B trying to view User A's order detail -> 404
        url_detail = reverse('dashboard:order_detail', args=[self.order_a.order_number])
        resp_detail = self.client.get(url_detail)
        self.assertEqual(resp_detail.status_code, 404)

    def test_user_order_cancellation(self):
        """Test K: Customer can cancel an unpaid pending order."""
        self.client.force_login(self.user_a)
        url_cancel = reverse('dashboard:order_cancel', args=[self.order_a.order_number])

        # GET method rejected
        resp_get = self.client.get(url_cancel)
        self.assertEqual(resp_get.status_code, 302)

        # POST method cancels order and pending payment
        resp_post = self.client.post(url_cancel)
        self.assertEqual(resp_post.status_code, 302)

        self.order_a.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order_a.order_status, Order.STATUS_CANCELLED)
        self.assertEqual(self.order_a.payment_status, Order.PAYMENT_CANCELLED)
        self.assertEqual(self.payment.status, Payment.STATUS_CANCELLED)
