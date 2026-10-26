from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
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
        cache.clear()
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
            'profile_type': 'personal',
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


# ==============================================================================
# PHASE 1 HOMEPAGE REDESIGN AUTOMATED VALIDATION
# ==============================================================================
class Phase1HomepageRedesignTests(TestCase):
    """
    Validation tests for Phase 1 Homepage and First-Impression Redesign.
    Ensures that first-time visitors immediately understand what UZYRA is,
    how it works, and how to create their profile.
    """

    def setUp(self):
        self.client = Client()
        self.user_password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="visitor@example.com",
            password=self.user_password,
            first_name="Alex",
            last_name="Cole",
            is_email_verified=True
        )
        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
            defaults={'full_name': 'Alex Cole', 'slug': 'alex-cole', 'phone': '+2348011112222'}
        )
        self.package = ProductPackage.objects.create(
            name="Smart NFC Card",
            code="smart-nfc-card",
            price_ngn=15000,
            description="High quality card",
            features="Feature A\nFeature B",
            is_active=True
        )

    def test_hero_communicates_product_and_ctas(self):
        """Unauthenticated visitor sees core message and immediate registration CTA."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Introduction,")
        self.assertContains(response, "One Tap Away.")
        self.assertContains(response, "Create Your Profile Free")
        self.assertContains(response, reverse('accounts:register'))
        self.assertContains(response, "#how-it-works")
        self.assertContains(response, "Zero Apps Needed")
        self.assertContains(response, "iOS & Android Native")

    def test_clarity_strip_pillars_present(self):
        """Homepage provides 5-second clarity across 3 core pillars."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Digital Profile First")
        self.assertContains(response, "Physical NFC Smart Card")
        self.assertContains(response, "Always Up to Date")

    def test_how_it_works_three_teaching_steps(self):
        """3 teaching steps explain registration -> link customization -> in-person tap."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How It Works in 3 Steps")
        self.assertContains(response, "Create Your Digital Profile")
        self.assertContains(response, "Customize & Get Your Link")
        self.assertContains(response, "Share Anywhere — Tap or Link")

    def test_personal_vs_business_differentiation(self):
        """Distinct sections for individuals and corporate teams with relevant CTAs."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "For Individuals & Professionals")
        self.assertContains(response, "Elevate Your Personal Brand")
        self.assertContains(response, "For Teams & Companies")
        self.assertContains(response, "Empower Your Entire Fleet")
        self.assertContains(response, reverse('core:contact'))

    def test_nfc_card_hardware_specifications(self):
        """Physical card companion clearly explained as independent from digital profile."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The NFC Smart Card Companion")
        self.assertContains(response, "Embedded NTAG216 Chip")
        self.assertContains(response, "Zero Battery & Charging")
        self.assertContains(response, "You do not need a physical card to use your digital profile")

    def test_packages_rendered_with_checkout_links(self):
        """Live ProductPackages render with prices in NGN and checkout links."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Smart NFC Card")
        self.assertContains(response, "₦15000")
        checkout_url = reverse('orders:checkout', kwargs={'package_code': self.package.code})
        self.assertContains(response, checkout_url)

    def test_authenticated_user_hero_actions(self):
        """Logged in user auto-redirects to dashboard on root, and sees profile CTA when explicitly viewing public landing."""
        self.client.login(email=self.user.email, password=self.user_password)
        # 1. Root access auto-redirects to dashboard overview
        root_response = self.client.get(reverse('core:home'))
        self.assertRedirects(root_response, reverse('dashboard:overview'))

        # 2. Explicit public view allows viewing landing page while authenticated
        response = self.client.get(reverse('core:home') + '?public=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Go to Your Digital Profile")
        self.assertContains(response, reverse('dashboard:profile_edit'))

    def test_faq_accordion_answers_card_requirement(self):
        """FAQ addresses common misconceptions including no requirement to buy card first."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Can I create a profile without buying a physical card?")
        self.assertContains(response, "Does the person tapping my card need to install an app?")
        self.assertContains(response, "Does the card work on both iPhone and Android?")


class Phase2OnboardingRedesignTests(TestCase):
    """
    Automated tests for UZYRA Phase 2:
    Registration polish, Guided 4-step onboarding wizard,
    Personal vs Business profiles, and profile editor improvements.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"
        self.user = User.objects.create_user(
            email="onboarding_user@example.com",
            password=self.password,
            first_name="Ada",
            last_name="Lovelace",
            is_email_verified=True
        )
        self.profile, _ = Profile.objects.get_or_create(user=self.user)

    def test_registration_view_renders_clarity_features(self):
        """Registration view includes trust strip, required indicators, and login link."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Your Account")
        self.assertContains(response, "Free Profile Creation")
        self.assertContains(response, "Instant Share Link")
        self.assertContains(response, "Already have an account?")
        self.assertContains(response, reverse('accounts:login'))

    def test_registration_validation_password_mismatch(self):
        """Form rejects mismatched passwords with inline error."""
        data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'new_user@example.com',
            'phone': '+2348011112222',
            'password': 'Password123!',
            'password_confirm': 'DifferentPassword123!',
            'agree_terms': True
        }
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match")

    def test_login_view_renders_polished_form(self):
        """Login page renders toggle password button and clean form."""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome Back")
        self.assertContains(response, "Sign In")
        self.assertContains(response, "togglePassword")

    def test_onboarding_requires_login(self):
        """Unauthenticated visitor is redirected to login."""
        response = self.client.get(reverse('dashboard:onboarding'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_onboarding_wizard_renders_steps(self):
        """Authenticated user accesses 4-step guided onboarding wizard."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('dashboard:onboarding'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome to STRIDE")
        self.assertContains(response, "Choose Your Profile Type")
        self.assertContains(response, "Personal Profile")
        self.assertContains(response, "Business Profile")

    def test_onboarding_completes_personal_profile(self):
        """Saving personal profile sets profile_type, title, bio, contacts, links, and generates slug."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Ada Lovelace',
            'title': 'Computing Pioneer & Consultant',
            'bio': 'Analytic engine programmer and mathematician.',
            'phone': '+2348012345678',
            'whatsapp': '+2348012345678',
            'email': 'ada@example.com',
            'website_url': 'https://adalovelace.io',
            'location': 'London / Lagos',
            'social_instagram': 'adalovelace',
            'social_linkedin': 'https://linkedin.com/in/ada-lovelace',
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:overview'))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, 'personal')
        self.assertEqual(self.profile.title, 'Computing Pioneer & Consultant')
        self.assertEqual(self.profile.phone, '+2348012345678')
        self.assertTrue(bool(self.profile.slug))
        self.assertTrue(self.profile.social_links.filter(platform='instagram').exists())
        self.assertTrue(self.profile.social_links.filter(platform='linkedin').exists())

    def test_onboarding_completes_business_profile(self):
        """Saving business profile sets profile_type, business_name, category, description, and slug."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'business',
            'full_name': 'Ada Lovelace',
            'business_name': 'Analytical Engines Ltd',
            'business_category': 'Technology & Computing',
            'business_description': 'Pioneering general-purpose computational architectures.',
            'phone': '+2348099998888',
            'whatsapp': '+2348099998888',
            'email': 'biz@example.com',
            'website_url': 'https://analyticalengines.com',
            'location': 'Lagos, Nigeria',
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:overview'))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, 'business')
        self.assertEqual(self.profile.business_name, 'Analytical Engines Ltd')
        self.assertEqual(self.profile.business_category, 'Technology & Computing')
        self.assertTrue(bool(self.profile.slug))

    def test_dashboard_overview_displays_onboarding_callout_for_incomplete_profile(self):
        """Incomplete profile displays prominent banner linking to onboarding."""
        self.profile.title = ""
        self.profile.business_name = ""
        self.profile.save()

        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finish Setting Up Your Profile")
        self.assertContains(response, reverse('dashboard:onboarding'))

    def test_profile_edit_renders_and_updates_profile_type(self):
        """Profile editor allows switching profile type between personal and business."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('dashboard:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Type")
        self.assertContains(response, "Personal Profile")
        # Business Profile mode selector shelved for v2 — not rendered in switcher
        self.assertNotContains(response, "edit-mode-business")

        # Submit change to business profile (backend still accepts it)
        edit_data = {
            'profile_type': 'business',
            'full_name': 'Ada Lovelace',
            'title': 'Managing Director',
            'business_name': 'Analytical Dynamics',
            'business_category': 'Technology',
            'email': 'ada@example.com',
        }
        post_resp = self.client.post(reverse('dashboard:profile_edit'), edit_data)
        self.assertEqual(post_resp.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, 'business')
        self.assertEqual(self.profile.business_name, 'Analytical Dynamics')


