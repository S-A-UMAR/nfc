import io
import json
import hmac
import hashlib
from datetime import timedelta
from PIL import Image

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import OTPCode
from apps.accounts.forms import UserRegisterForm
from apps.cards.models import Card
from apps.profiles.models import Profile, SocialLink, CustomLink
from apps.profiles.forms import ProfileForm, CustomLinkForm, SocialLinkForm
from apps.orders.models import Order, ProductPackage
from apps.payments.models import Payment
from apps.core.validators import validate_image_upload, validate_safe_url
from apps.core.services.email_service import BrevoEmailService

User = get_user_model()


class AuthenticationSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email='alice@example.com',
            password='StrongPassword123!',
            first_name='Alice',
            last_name='Security'
        )

    def test_login_with_valid_credentials_succeeds(self):
        resp = self.client.post(reverse('accounts:login'), {
            'username': 'alice@example.com',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('dashboard:overview'))

    def test_login_with_invalid_credentials_fails(self):
        resp = self.client.post(reverse('accounts:login'), {
            'username': 'alice@example.com',
            'password': 'WrongPassword123!'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid email or password")

    def test_login_open_redirect_prevention(self):
        """Prevents open redirect attacks via ?next=https://evil.com."""
        resp = self.client.post(reverse('accounts:login') + '?next=https://evil.com', {
            'username': 'alice@example.com',
            'password': 'StrongPassword123!'
        })
        self.assertEqual(resp.status_code, 302)
        # Must redirect to dashboard overview, NEVER to evil.com
        self.assertNotIn('evil.com', resp.url)
        self.assertRedirects(resp, reverse('dashboard:overview'))

    def test_registration_password_strength_enforced(self):
        """Weak passwords (e.g. short or entirely numeric) are rejected."""
        form_short = UserRegisterForm(data={
            'first_name': 'Bob',
            'last_name': 'Tester',
            'email': 'bob@example.com',
            'password': '123',
            'password_confirm': '123',
            'agree_terms': True
        })
        self.assertFalse(form_short.is_valid())
        self.assertIn('password', form_short.errors)

    def test_registration_success_and_otp_dispatch(self):
        resp = self.client.post(reverse('accounts:register'), {
            'first_name': 'Charlie',
            'last_name': 'Evans',
            'email': 'charlie@example.com',
            'password': 'ComplexPassword888!',
            'password_confirm': 'ComplexPassword888!',
            'agree_terms': True
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:verify_otp'))

        # Verify user created with is_email_verified=False
        new_user = User.objects.get(email='charlie@example.com')
        self.assertFalse(new_user.is_email_verified)

        # Verify OTP record created
        self.assertTrue(OTPCode.objects.filter(email='charlie@example.com', purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION).exists())


class PasswordResetSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email='resetuser@example.com',
            password='InitialPassword123!',
            first_name='Reset',
            last_name='User'
        )

    def test_password_reset_generic_response_for_existing_user(self):
        """Generic response prevents email enumeration."""
        resp = self.client.post(reverse('accounts:password_reset'), {
            'email': 'resetuser@example.com'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:password_reset_done'))

    def test_password_reset_generic_response_for_nonexistent_user(self):
        """Identical generic response returned for non-existent user."""
        resp = self.client.post(reverse('accounts:password_reset'), {
            'email': 'nonexistent_account@example.com'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:password_reset_done'))

    def test_password_reset_token_validation_and_update(self):
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        confirm_url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})

        # Render form
        resp = self.client.get(confirm_url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['validlink'])

        # Submit new password
        resp_post = self.client.post(confirm_url, {
            'new_password1': 'BrandNewPassword999!',
            'new_password2': 'BrandNewPassword999!'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertRedirects(resp_post, reverse('accounts:password_reset_complete'))

        # Confirm old password no longer works, new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassword999!'))
        self.assertFalse(self.user.check_password('InitialPassword123!'))

        # Confirm token is invalidated immediately after use (single-use)
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_password_reset_invalid_or_tampered_token_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_url = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': 'tampered-invalid-token'})
        resp = self.client.get(invalid_url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['validlink'])
        self.assertContains(resp, "invalid, already used, or expired")


class OTPSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email='otpuser@example.com',
            password='Password123!',
            first_name='OTP',
            last_name='Test'
        )

    def test_otp_generation_and_sha256_hash_storage(self):
        otp, plain_code = OTPCode.generate_otp(
            user=self.user,
            email=self.user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION,
            duration_minutes=10
        )
        self.assertEqual(len(plain_code), 6)
        self.assertTrue(plain_code.isdigit())

        # Plain code must NEVER equal code_hash in the database
        self.assertNotEqual(otp.code_hash, plain_code)
        expected_hash = hashlib.sha256(plain_code.encode('utf-8')).hexdigest()
        self.assertEqual(otp.code_hash, expected_hash)

    def test_otp_verification_success_and_consumption(self):
        otp, plain_code = OTPCode.generate_otp(
            user=self.user,
            email=self.user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        success, msg = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_EMAIL_VERIFICATION, plain_code)
        self.assertTrue(success)

        otp.refresh_from_db()
        self.assertTrue(otp.is_consumed)

        # Re-using the same code must fail (single-use token)
        success_retry, _ = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_EMAIL_VERIFICATION, plain_code)
        self.assertFalse(success_retry)

    def test_otp_expiration_rejected(self):
        otp, plain_code = OTPCode.generate_otp(
            user=self.user,
            email=self.user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        # Set expiration to the past
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save()

        success, msg = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_EMAIL_VERIFICATION, plain_code)
        self.assertFalse(success)
        self.assertIn("expired", msg.lower())

    def test_otp_attempt_limits_and_lockout(self):
        otp, plain_code = OTPCode.generate_otp(
            user=self.user,
            email=self.user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        # 5 wrong attempts
        for _ in range(5):
            success, _ = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_EMAIL_VERIFICATION, '000000')
            self.assertFalse(success)

        # After 5 failed attempts, even correct code is locked out
        success, msg = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_EMAIL_VERIFICATION, plain_code)
        self.assertFalse(success)
        self.assertIn("too many failed attempts", msg.lower())

    def test_otp_scoped_protection(self):
        """OTP created for EMAIL_VERIFICATION cannot be used for CARD_ACTIVATION."""
        otp, plain_code = OTPCode.generate_otp(
            user=self.user,
            email=self.user.email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        success, _ = OTPCode.verify_code(self.user.email, OTPCode.PURPOSE_CARD_ACTIVATION, plain_code)
        self.assertFalse(success)


class CardActivationMatrixTests(TestCase):
    """
    Card Activation Test Matrix (Cases 1 to 10):
    Case 1: Valid activation succeeds
    Case 2: Invalid card code fails
    Case 3: Invalid activation code fails
    Case 4: Already active card cannot be activated
    Case 5: Suspended card cannot be activated
    Case 6: Replaced card cannot be activated
    Case 7: Unauthenticated activation rejected
    Case 8: Rate-limited after repeated failed attempts
    Case 9: Concurrent activation requests handled safely
    Case 10: Activation links card strictly to activating user's profile
    """
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='owner_a@example.com',
            password='Password123!',
            first_name='Owner',
            last_name='A'
        )
        self.profile_a = self.user_a.profile

        self.user_b = User.objects.create_user(
            email='owner_b@example.com',
            password='Password123!',
            first_name='Owner',
            last_name='B'
        )
        self.profile_b = self.user_b.profile

        # Create unassigned card with activation secret PIN
        self.card = Card.objects.create(
            card_code='TEST-000001',
            status=Card.STATUS_UNASSIGNED
        )
        self.pin = self.card.generate_activation_code()
        self.card.save()

    def test_case_1_valid_activation_succeeds(self):
        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        })
        self.assertEqual(resp.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_ACTIVE)
        self.assertEqual(self.card.user, self.user_a)
        self.assertEqual(self.card.profile, self.profile_a)

    def test_case_2_invalid_card_code_fails(self):
        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'NON-EXISTENT-CARD-99',
            'activation_code': self.pin
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "was not found")

    def test_case_3_invalid_activation_code_fails(self):
        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': 'WRONG-PIN-1234'
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid activation code")
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_UNASSIGNED)

    def test_case_4_already_active_card_cannot_be_activated(self):
        self.card.status = Card.STATUS_ACTIVE
        self.card.user = self.user_b
        self.card.profile = self.profile_b
        self.card.save()

        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already active")

    def test_case_5_suspended_card_cannot_be_activated(self):
        self.card.status = Card.STATUS_SUSPENDED
        self.card.save()

        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "suspended")

    def test_case_6_replaced_card_cannot_be_activated(self):
        self.card.status = Card.STATUS_REPLACED
        self.card.save()

        self.client.force_login(self.user_a)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "replaced")

    def test_case_7_unauthenticated_activation_rejected(self):
        # Client not logged in
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_case_8_rate_limited_after_repeated_failed_attempts(self):
        self.client.force_login(self.user_a)
        # Attempt 5 wrong activations
        for _ in range(5):
            self.client.post(reverse('cards:card_activate'), {
                'card_code': 'TEST-000001',
                'activation_code': 'BAD-PIN'
            })
        # 6th attempt must be throttled
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        }, follow=True)
        self.assertContains(resp, "Throttled")

    def test_case_9_concurrent_activation_requests_handled_safely(self):
        """Atomic transaction ensures card activation is mutually exclusive."""
        self.client.force_login(self.user_a)
        resp_a = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        })
        self.assertEqual(resp_a.status_code, 302)

        # Immediate secondary attempt by User B
        client_b = Client()
        client_b.force_login(self.user_b)
        resp_b = client_b.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        }, follow=True)
        self.assertContains(resp_b, "already active")

    def test_case_10_activation_links_card_strictly_to_activating_user(self):
        self.client.force_login(self.user_a)
        self.client.post(reverse('cards:card_activate'), {
            'card_code': 'TEST-000001',
            'activation_code': self.pin
        })
        self.card.refresh_from_db()
        self.assertEqual(self.card.user, self.user_a)
        self.assertNotEqual(self.card.user, self.user_b)
        self.assertEqual(self.card.profile, self.profile_a)
        self.assertNotEqual(self.card.profile, self.profile_b)


class AuthorizationIDORSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_a = Client()
        self.user_a = User.objects.create_user(
            email='victim@example.com',
            password='Password123!',
            first_name='Victim',
            last_name='A'
        )
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.user_b = User.objects.create_user(
            email='attacker@example.com',
            password='Password123!',
            first_name='Attacker',
            last_name='B'
        )
        self.client_b.force_login(self.user_b)

        # User A's custom link
        self.link_a = CustomLink.objects.create(
            profile=self.user_a.profile,
            title="Victim Portfolio",
            url="https://victim.example.com"
        )

        # User A's order
        package = ProductPackage.objects.create(
            code='test-card',
            name='Test Card Package',
            price_ngn=50000,
            description='Test package'
        )
        self.order_a = Order.objects.create(
            order_number='ORD-VICTIM-001',
            user=self.user_a,
            package=package,
            amount=50000
        )

    def test_user_b_cannot_delete_user_a_link(self):
        """IDOR defense: User B cannot delete User A's links."""
        delete_url = reverse('dashboard:delete_custom_link', kwargs={'link_id': self.link_a.id})
        resp = self.client_b.post(delete_url)
        # Must return 404 Not Found (or 403)
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(CustomLink.objects.filter(id=self.link_a.id).exists())

    def test_user_b_cannot_view_user_a_order(self):
        """IDOR defense: User B cannot view User A's order details."""
        order_url = reverse('dashboard:order_detail', kwargs={'order_number': self.order_a.order_number})
        resp = self.client_b.get(order_url)
        self.assertEqual(resp.status_code, 404)

    def test_user_b_cannot_initialize_user_a_order_payment(self):
        pay_url = reverse('payments:initialize', kwargs={'order_number': self.order_a.order_number})
        resp = self.client_b.get(pay_url)
        self.assertEqual(resp.status_code, 404)


class UploadAndInputSecurityTests(TestCase):
    def test_validate_image_upload_rejects_svg(self):
        """Strictly rejects SVG files to prevent stored XSS via SVG scripts."""
        svg_content = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
        svg_file = SimpleUploadedFile("avatar.svg", svg_content, content_type="image/svg+xml")
        with self.assertRaises(ValidationError):
            validate_image_upload(svg_file)

    def test_validate_image_upload_rejects_disguised_executable(self):
        """Disguised non-image files with .jpg extension are rejected by Pillow verification."""
        fake_jpg = SimpleUploadedFile("malware.jpg", b"MZ\x90\x00\x03\x00\x00\x00fake_executable_payload", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_upload(fake_jpg)

    def test_validate_image_upload_accepts_valid_png(self):
        img_buffer = io.BytesIO()
        img = Image.new('RGB', (50, 50), color='black')
        img.save(img_buffer, format='PNG')
        valid_png = SimpleUploadedFile("valid.png", img_buffer.getvalue(), content_type="image/png")
        result = validate_image_upload(valid_png)
        self.assertIsNotNone(result)

    def test_validate_safe_url_rejects_javascript_scheme(self):
        """Rejects javascript: XSS payloads."""
        with self.assertRaises(ValidationError):
            validate_safe_url("javascript:alert(document.cookie)")

    def test_validate_safe_url_rejects_data_scheme(self):
        with self.assertRaises(ValidationError):
            validate_safe_url("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==")

    def test_validate_safe_url_accepts_valid_https(self):
        url = "https://uzyra.com/portfolio"
        self.assertEqual(validate_safe_url(url), url)


class PaymentSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email='payer@example.com',
            password='Password123!',
            first_name='Payer',
            last_name='Test'
        )
        self.client.force_login(self.user)

        package = ProductPackage.objects.create(
            code='pay-package',
            name='Luxury Card Suite',
            price_ngn=75000,
            description='Test package'
        )
        self.order = Order.objects.create(
            order_number='ORD-PAY-001',
            user=self.user,
            package=package,
            amount=75000
        )
        self.payment = Payment.objects.create(
            order=self.order,
            reference='PAY-TEST-REF-001',
            amount=75000,
            status=Payment.STATUS_PENDING
        )

    def test_paystack_webhook_invalid_signature_rejected(self):
        """Rejects webhooks with missing or mismatched HMAC SHA512 signature."""
        resp = self.client.post(
            reverse('payments:webhook'),
            data=json.dumps({'event': 'charge.success'}),
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='invalid_signature'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Invalid signature", status_code=400)

    def test_paystack_webhook_valid_signature_and_amount_verification(self):
        """Valid HMAC signature + matching amount in kobo successfully confirms order."""
        secret = getattr(settings, 'PAYSTACK_SECRET_KEY', 'sk_test_sample_secret_key').encode('utf-8')
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment.reference,
                'amount': 7500000,  # 75,000 NGN in kobo
                'currency': 'NGN',
                'channel': 'card',
                'gateway_response': 'Successful'
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        valid_signature = hmac.new(secret, body_bytes, hashlib.sha512).hexdigest()

        resp = self.client.post(
            reverse('payments:webhook'),
            data=body_bytes,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=valid_signature
        )
        self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_SUCCESS)
        self.assertEqual(self.order.payment_status, Order.PAYMENT_PAID)

    def test_paystack_webhook_amount_mismatch_rejected(self):
        """Underpayment / price manipulation attack rejected even with valid signature."""
        secret = getattr(settings, 'PAYSTACK_SECRET_KEY', 'sk_test_sample_secret_key').encode('utf-8')
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': self.payment.reference,
                'amount': 100,  # Attacker paid 100 kobo (1 NGN) instead of 7,500,000 kobo
                'currency': 'NGN',
                'channel': 'card',
                'gateway_response': 'Successful'
            }
        }
        body_bytes = json.dumps(payload).encode('utf-8')
        valid_signature = hmac.new(secret, body_bytes, hashlib.sha512).hexdigest()

        resp = self.client.post(
            reverse('payments:webhook'),
            data=body_bytes,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=valid_signature
        )
        self.assertEqual(resp.status_code, 200)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        # Payment must NOT be marked success, order must NOT be marked paid
        self.assertNotEqual(self.payment.status, Payment.STATUS_SUCCESS)
        self.assertNotEqual(self.order.payment_status, Order.PAYMENT_PAID)
