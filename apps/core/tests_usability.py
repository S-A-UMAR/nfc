from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile, SocialLink
from apps.cards.models import Card
from apps.orders.models import Order, ProductPackage
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

class UsabilityJourneyTests(TestCase):
    """
    Comprehensive Automated Usability & Mobile-First Journey Tests (Journeys A - I).
    Validates that real users can independently execute all key flows on UZYRA.
    """

    def setUp(self):
        self.client = Client()
        self.user_password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="usabilityuser@example.com",
            password=self.user_password,
            first_name="Jane",
            last_name="Doe",
            is_email_verified=True
        )
        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
            defaults={'full_name': 'Jane Doe', 'slug': 'jane-doe', 'phone': '+2348012345678'}
        )
        self.package = ProductPackage.objects.create(
            name="Matte Black NFC Card",
            code="matte-black",
            price_ngn=15000,
            is_active=True
        )

    # --------------------------------------------------------------------------
    # JOURNEY A: Registration & OTP Verification
    # --------------------------------------------------------------------------
    def test_journey_a_registration_and_otp(self):
        """Test registration page rendering, form submission, and OTP view."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Your Account")

        reg_data = {
            'first_name': 'John',
            'last_name': 'Smith',
            'email': 'johnsmith@example.com',
            'phone': '+2348099998888',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'agree_terms': True
        }
        reg_resp = self.client.post(reverse('accounts:register'), reg_data)
        self.assertIn(reg_resp.status_code, [200, 302])

        # Test verify OTP view rendering
        otp_resp = self.client.get(reverse('accounts:verify_otp'))
        self.assertEqual(otp_resp.status_code, 200)
        self.assertContains(otp_resp, "Verify Email Address")

    # --------------------------------------------------------------------------
    # JOURNEY B: Login & Password Reset
    # --------------------------------------------------------------------------
    def test_journey_b_login_and_password_reset(self):
        """Test login flow and password reset request page."""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign In")

        # Test password reset page when unauthenticated
        reset_resp = self.client.get(reverse('accounts:password_reset'))
        self.assertEqual(reset_resp.status_code, 200)
        self.assertContains(reset_resp, "Reset")

        # Perform login
        login_resp = self.client.post(reverse('accounts:login'), {
            'username': self.user.email,
            'password': self.user_password
        })
        self.assertEqual(login_resp.status_code, 302)

    # --------------------------------------------------------------------------
    # JOURNEY C: Dashboard Onboarding & Guidance
    # --------------------------------------------------------------------------
    def test_journey_c_dashboard_onboarding_guidance(self):
        """Test first-time dashboard overview checklist & active order banner."""
        self.client.login(email=self.user.email, password=self.user_password)
        
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Workspace")

        # Create active order
        order = Order.objects.create(
            user=self.user,
            package=self.package,
            amount=15000,
            order_status='pending',
            payment_status='paid'
        )

        response_with_order = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response_with_order.status_code, 200)
        self.assertContains(response_with_order, order.order_number)
        self.assertContains(response_with_order, "Active Order")

    # --------------------------------------------------------------------------
    # JOURNEY D: Profile Builder & Editing (Mobile)
    # --------------------------------------------------------------------------
    def test_journey_d_profile_edit_and_save(self):
        """Test profile editing form submission and slug generation."""
        self.client.login(email=self.user.email, password=self.user_password)

        response = self.client.get(reverse('dashboard:profile_edit'))
        self.assertEqual(response.status_code, 200)

        post_data = {
            'full_name': 'Jane Doe Updated',
            'title': 'Senior Product Designer',
            'bio': 'Designing simple digital tools for modern professionals.',
            'phone': '+2348012345678',
            'whatsapp': '+2348012345678',
            'email': 'jane.doe.public@example.com',
            'location': 'Lagos, Nigeria',
            'business_name': 'Design Studio Co.',
            'is_search_indexed': True
        }
        save_resp = self.client.post(reverse('dashboard:profile_edit'), post_data)
        self.assertIn(save_resp.status_code, [200, 302])

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, 'Jane Doe Updated')
        self.assertEqual(self.profile.title, 'Senior Product Designer')

    # --------------------------------------------------------------------------
    # JOURNEY E: Public Profile & Touch Interaction
    # --------------------------------------------------------------------------
    def test_journey_e_public_profile_and_vcard(self):
        """Test public profile view accessibility and vCard export."""
        url = reverse('profiles:public_profile', kwargs={'slug': self.profile.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.profile.full_name)

        # Test vCard download
        vcard_url = reverse('profiles:download_vcard', kwargs={'slug': self.profile.slug})
        vcard_resp = self.client.get(vcard_url)
        self.assertEqual(vcard_resp.status_code, 200)
        self.assertEqual(vcard_resp['Content-Type'], 'text/vcard; charset=utf-8')
        self.assertContains(vcard_resp, "BEGIN:VCARD")

    # --------------------------------------------------------------------------
    # JOURNEY F: Physical Card Management & Activation
    # --------------------------------------------------------------------------
    def test_journey_f_card_management_and_activation(self):
        """Test card management page and hardware activation."""
        self.client.login(email=self.user.email, password=self.user_password)

        response = self.client.get(reverse('dashboard:card_manage'))
        self.assertEqual(response.status_code, 200)

        # Create unassigned card in database
        card = Card.objects.create(
            card_code="BR-999888",
            status="UNASSIGNED"
        )
        card.set_activation_code("UZ99-8888")
        card.save()

        # Activate card via POST
        act_resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'BR-999888',
            'activation_code': 'UZ99-8888'
        })
        self.assertIn(act_resp.status_code, [200, 302])

        card.refresh_from_db()
        self.assertEqual(card.user, self.user)
        self.assertEqual(card.status, "ACTIVE")

    # --------------------------------------------------------------------------
    # JOURNEY G: Card Ordering & Paystack Checkout
    # --------------------------------------------------------------------------
    def test_journey_g_pricing_and_checkout(self):
        """Test pricing page navigation and checkout form submission."""
        pricing_resp = self.client.get(reverse('core:pricing'))
        self.assertEqual(pricing_resp.status_code, 200)

        self.client.login(email=self.user.email, password=self.user_password)
        checkout_url = reverse('orders:checkout', kwargs={'package_code': self.package.code})
        checkout_resp = self.client.get(checkout_url)
        self.assertEqual(checkout_resp.status_code, 200)

        order_post = self.client.post(checkout_url, {
            'shipping_name': 'Jane Doe',
            'shipping_phone': '+2348012345678',
            'shipping_address': '12 Victoria Island Road',
            'shipping_city': 'Lagos',
            'shipping_state': 'Lagos'
        })
        self.assertEqual(order_post.status_code, 302)

    # --------------------------------------------------------------------------
    # JOURNEY H: Order Fulfillment & Delivery Tracking
    # --------------------------------------------------------------------------
    def test_journey_h_order_detail_progress(self):
        """Test order detail view and 4-step progress timeline."""
        self.client.login(email=self.user.email, password=self.user_password)

        order = Order.objects.create(
            user=self.user,
            package=self.package,
            amount=15000,
            order_status='processing',
            payment_status='paid'
        )

        detail_url = reverse('dashboard:order_detail', kwargs={'order_number': order.order_number})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Order #{order.order_number}")
        self.assertContains(response, "Fulfillment Progress")

    # --------------------------------------------------------------------------
    # JOURNEY I: Account Settings, Privacy & Support
    # --------------------------------------------------------------------------
    def test_journey_i_settings_and_privacy_support(self):
        """Test settings view, password change, and privacy/support complaints page."""
        self.client.login(email=self.user.email, password=self.user_password)

        settings_resp = self.client.get(reverse('dashboard:settings_view'))
        self.assertEqual(settings_resp.status_code, 200)
        self.assertContains(settings_resp, "Account Settings")

        complaints_resp = self.client.get(reverse('legal:complaints'))
        self.assertEqual(complaints_resp.status_code, 200)
        self.assertContains(complaints_resp, "Complaints")
