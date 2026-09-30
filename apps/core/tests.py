from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile
from apps.cards.models import Card, CardEvent
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

class PlatformCoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='TestPassword123!',
            first_name='Test',
            last_name='User'
        )
        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
            defaults={
                'slug': 'test-user',
                'full_name': 'Test User',
                'phone': '+2348012345678',
                'whatsapp': '+2348012345678',
                'email': 'testuser@example.com'
            }
        )
        self.active_card = Card.objects.create(
            card_code='BR-999001',
            user=self.user,
            profile=self.profile,
            status=Card.STATUS_ACTIVE
        )
        self.lost_card = Card.objects.create(
            card_code='BR-999002',
            user=self.user,
            status=Card.STATUS_LOST
        )
        self.unassigned_card = Card.objects.create(
            card_code='BR-999003',
            status=Card.STATUS_UNASSIGNED
        )
        self.package = ProductPackage.objects.create(
            code='test-card-pkg',
            name='Test Smart Card',
            package_type='card_only',
            price_ngn=25000,
            description='Test card description',
            features='Feature 1\nFeature 2'
        )

    def test_homepage_renders(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'YOUR IDENTITY. YOUR BUSINESS. ONE TOUCH.')

    def test_pricing_renders_packages(self):
        response = self.client.get(reverse('core:pricing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Smart Card')

    def test_nfc_active_card_redirects_to_profile(self):
        """Active card /c/BR-999001/ must redirect to /u/test-user/ and log events."""
        response = self.client.get(f'/c/{self.active_card.card_code}/', follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.profile.slug, response.url)

        # Check event logged
        self.assertTrue(CardEvent.objects.filter(card=self.active_card).exists())
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile).exists())

    def test_nfc_lost_card_renders_security_notice(self):
        response = self.client.get(f'/c/{self.lost_card.card_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Card Inactive')
        self.assertContains(response, 'reported lost')

    def test_nfc_unassigned_card_renders_activation_page(self):
        response = self.client.get(f'/c/{self.unassigned_card.card_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activate Smart Card')

    def test_public_profile_and_vcard_generation(self):
        # Public Profile HTML
        response = self.client.get(reverse('profiles:public_profile', kwargs={'slug': self.profile.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test User')

        # Download vCard .vcf
        vcard_response = self.client.get(reverse('profiles:download_vcard', kwargs={'slug': self.profile.slug}))
        self.assertEqual(vcard_response.status_code, 200)
        self.assertEqual(vcard_response['Content-Type'], 'text/vcard; charset=utf-8')
        self.assertIn('BEGIN:VCARD', vcard_response.content.decode('utf-8'))
        self.assertIn('FN:Test User', vcard_response.content.decode('utf-8'))

    def test_customer_registration_creates_profile(self):
        reg_data = {
            'first_name': 'New',
            'last_name': 'Customer',
            'email': 'newcustomer@example.com',
            'phone': '+2348099887766',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'agree_terms': 'on',
        }
        response = self.client.post(reverse('accounts:register'), reg_data, follow=True)
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(email='newcustomer@example.com')
        self.assertIsNotNone(new_user.profile)
        self.assertEqual(new_user.profile.full_name, 'New Customer')

    @override_settings(PAYSTACK_TEST_MODE=True)
    def test_order_creation_and_payment_simulation(self):
        self.client.force_login(self.user)
        checkout_data = {
            'shipping_name': 'Test User',
            'shipping_phone': '+2348012345678',
            'shipping_address': '123 Test Street',
            'shipping_city': 'Lagos',
            'shipping_state': 'Lagos State',
        }
        response = self.client.post(reverse('orders:checkout', kwargs={'package_code': self.package.code}), checkout_data, follow=True)
        self.assertEqual(response.status_code, 200)

        order = Order.objects.filter(user=self.user).latest('created_at')
        self.assertEqual(order.package, self.package)
        self.assertEqual(order.amount, 25000)

        # Payment verification simulator
        payment = Payment.objects.create(
            order=order,
            reference=f"REF-{order.order_number}",
            amount=order.amount
        )
        verify_response = self.client.post(reverse('payments:verify'), {
            'reference': payment.reference,
            'simulated': 'true'
        }, follow=True)
        self.assertEqual(verify_response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)

    def test_analytics_api_beacon(self):
        payload = {
            'profile_slug': self.profile.slug,
            'event_type': 'whatsapp_click',
            'target_label': 'WhatsApp Chat'
        }
        response = self.client.post(
            reverse('analytics:track_event'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile, event_type='whatsapp_click').exists())
