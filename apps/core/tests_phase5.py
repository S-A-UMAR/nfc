import hmac
import hashlib
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile
from apps.cards.models import Card
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.core.models import ContactMessage

User = get_user_model()


class Phase5LaunchGateSecurityAndQATests(TestCase):
    def setUp(self):
        self.client = Client()

        # User A (Owner)
        self.user_a = User.objects.create_user(
            email='launch.usera@example.com',
            password='Password123!',
            first_name='Launch',
            last_name='UserA'
        )
        self.profile_a = self.user_a.profile
        self.profile_a.full_name = 'Launch User A'
        self.profile_a.slug = 'launch-user-a'
        self.profile_a.save()

        # User B (Attacker / Unrelated User)
        self.user_b = User.objects.create_user(
            email='launch.userb@example.com',
            password='Password123!',
            first_name='Launch',
            last_name='UserB'
        )
        self.profile_b = self.user_b.profile
        self.profile_b.full_name = 'Launch User B'
        self.profile_b.slug = 'launch-user-b'
        self.profile_b.save()

        # Card assigned to User A
        self.card_a = Card.objects.create(
            card_code='UZ-QA-000001',
            user=self.user_a,
            profile=self.profile_a,
            status=Card.STATUS_ACTIVE
        )

        # Unassigned Card
        self.card_unassigned = Card.objects.create(
            card_code='UZ-QA-000002',
            status=Card.STATUS_UNASSIGNED
        )

        # Package & Order for User A
        self.package = ProductPackage.objects.create(
            code='qa-nfc-pkg',
            name='QA NFC Package',
            package_type='card_only',
            price_ngn=15000,
            is_active=True
        )
        self.order_a = Order.objects.create(
            user=self.user_a,
            package=self.package,
            amount=15000,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED
        )

    # ── 1. AUTHENTICATION & SECURITY AUDIT ──────────────────────────────────
    def test_password_reset_generic_response_prevents_enumeration(self):
        """Password reset request returns success message for non-existent emails to prevent enumeration."""
        url = reverse('accounts:password_reset')
        response = self.client.post(url, {'email': 'nonexistent.user.999@example.com'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'If an account exists')

    def test_invalid_login_credentials_handled_safely(self):
        """Invalid login credentials return clear error without technical details."""
        url = reverse('accounts:login')
        response = self.client.post(url, {'username': 'launch.usera@example.com', 'password': 'WrongPassword999!'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid email or password')

    # ── 2. NFC SMART CARD & ROUTING AUDIT ────────────────────────────────────
    def test_active_nfc_card_redirects_to_public_profile(self):
        """Active NFC card redirects HTTP 302 directly to assigned public profile."""
        url = f"/c/{self.card_a.card_code}/"
        response = self.client.get(url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/u/{self.profile_a.slug}/", response.url)

    def test_unassigned_nfc_card_renders_activation_page(self):
        """Unassigned NFC card renders activation page without exposing private customer data."""
        url = f"/c/{self.card_unassigned.card_code}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activate Smart Card')
        self.assertNotContains(response, 'launch.usera@example.com')

    def test_lost_card_renders_security_notice(self):
        """Card marked LOST stops profile redirects and renders security notice."""
        self.card_a.status = Card.STATUS_LOST
        self.card_a.save()
        url = f"/c/{self.card_a.card_code}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This card has been reported lost')

    # ── 3. IDOR & AUTHORIZATION AUDIT ───────────────────────────────────────
    def test_idor_user_b_cannot_view_or_cancel_user_a_order(self):
        """User B cannot view or cancel User A's order."""
        self.client.force_login(self.user_b)

        # Detail view isolation
        url_detail = reverse('dashboard:order_detail', args=[self.order_a.order_number])
        resp_detail = self.client.get(url_detail)
        self.assertEqual(resp_detail.status_code, 404)

        # Cancel action isolation
        url_cancel = reverse('dashboard:order_cancel', args=[self.order_a.order_number])
        resp_cancel = self.client.post(url_cancel)
        self.assertEqual(resp_cancel.status_code, 404)

        self.order_a.refresh_from_db()
        self.assertNotEqual(self.order_a.order_status, Order.STATUS_CANCELLED)

    def test_idor_user_b_cannot_edit_user_a_profile(self):
        """User B submitting profile edits does not modify User A's profile data."""
        self.client.force_login(self.user_b)
        url_edit = reverse('dashboard:profile_edit')

        self.client.post(url_edit, {
            'full_name': 'Attacker Overwrite',
            'title': 'Hacker',
            'bio': 'Tampered bio',
            'business_name': 'Hacked LLC'
        })

        self.profile_a.refresh_from_db()
        self.profile_b.refresh_from_db()

        # User A profile remains untouched
        self.assertEqual(self.profile_a.full_name, 'Launch User A')
        # User B profile was updated
        self.assertEqual(self.profile_b.full_name, 'Attacker Overwrite')

    # ── 4. WEBHOOK & PAYMENT AUDIT ──────────────────────────────────────────
    def test_paystack_webhook_forged_signature_returns_400(self):
        """Paystack webhook with invalid signature returns HTTP 400."""
        url = reverse('payments:webhook')
        payload = json.dumps({"event": "charge.success", "data": {"reference": "REF123"}})
        response = self.client.post(
            url,
            data=payload,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='forged_sig_123'
        )
        self.assertEqual(response.status_code, 400)

    # ── 5. SEO & ROBOTS DISALLOW AUDIT ──────────────────────────────────────
    def test_robots_txt_disallows_private_endpoints(self):
        """robots.txt explicitly disallows search engine crawling of private areas."""
        url = reverse('robots_txt')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Disallow: /dashboard/')
        self.assertContains(response, 'Disallow: /operations/')
        self.assertContains(response, 'Disallow: /admin/')

    def test_dashboard_base_contains_noindex_meta_tag(self):
        """Dashboard pages include noindex, nofollow robots meta tag."""
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex, nofollow">')
