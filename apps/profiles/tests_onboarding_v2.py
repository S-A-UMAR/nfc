from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile

User = get_user_model()


class FullScreenTwoStepOnboardingTests(TestCase):
    """
    Test suite for STRIDE Full-Screen Two-Step Onboarding:
    - Screen 1: Identity & Persona (Personal vs Business)
    - Screen 2: Connect & Launch (Channels + Live Preview + Publication)
    - Full-screen distraction-free layout (no marketing navbar, no footer)
    - Validation and automatic satisfaction of `is_profile_configured`
    - Preserving existing profiles and handling skipped optional fields
    """

    def setUp(self):
        self.password = 'StrongP@ss123!'
        self.user = User.objects.create_user(
            email='new_onboarder@example.com',
            password=self.password,
            first_name='Kola',
            last_name='Adeleke',
            is_active=True
        )
        self.profile = getattr(self.user, 'profile', None)
        if not self.profile:
            self.profile = Profile.objects.create(
                user=self.user,
                full_name='Kola Adeleke',
                email=self.user.email
            )

    def test_fullscreen_onboarding_layout_removes_marketing_navbar_and_footer(self):
        """Onboarding renders a distraction-free full-screen layout without marketing nav or footer."""
        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('dashboard:onboarding'))
        self.assertEqual(response.status_code, 200)

        # Asserts dedicated minimal brand top bar
        self.assertContains(response, 'onboarding-top-bar')
        self.assertContains(response, 'Step 1 of 2: Your Identity')
        self.assertContains(response, 'full-screen-onboarding')

        # Asserts marketing floating navbar items are NOT rendered
        self.assertNotContains(response, 'class="navbar-nav"')
        self.assertNotContains(response, 'href="/pricing/"')
        self.assertNotContains(response, 'href="/websites/"')

    def test_personal_onboarding_completes_and_sets_configured(self):
        """Personal onboarding completes with role/title and verifies is_profile_configured."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Kola Adeleke',
            'title': 'Senior Product Designer',
            'bio': 'Designing accessible contactless identities.',
            'phone': '+2348012345678',
            'whatsapp': '+2348012345678',
            'email': 'kola@example.com',
            'website_url': 'https://kola.design',
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:overview'))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, 'personal')
        self.assertEqual(self.profile.title, 'Senior Product Designer')
        self.assertEqual(self.profile.bio, 'Designing accessible contactless identities.')
        self.assertTrue(bool(self.profile.slug))

        # Check configuration invariant
        is_configured = bool(self.profile.slug and (self.profile.title or self.profile.business_name))
        self.assertTrue(is_configured)

    def test_personal_onboarding_skipping_optional_title_defaults_safely(self):
        """Skipping optional title during personal onboarding defaults to 'Professional'."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Amina Garba',
            'title': '',  # skipped
            'bio': '',    # skipped
            'phone': '+2348099887766',
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, 'Amina Garba')
        self.assertEqual(self.profile.title, 'Professional')  # Safely defaulted!
        self.assertTrue(bool(self.profile.slug))

        is_configured = bool(self.profile.slug and (self.profile.title or self.profile.business_name))
        self.assertTrue(is_configured)

    def test_business_onboarding_completes_and_sets_configured(self):
        """Business onboarding sets company name, category, and representative."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'business',
            'full_name': 'Umar Sani',
            'business_name': 'STRIDE Technologies Ltd',
            'business_category': 'Hardware & Connected Identity',
            'business_description': 'Next-generation smart NFC infrastructure.',
            'phone': '+2348000000000',
            'whatsapp': '+2348000000000',
            'email': 'contact@strideid.com',
            'website_url': 'https://strideid.com',
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.profile_type, 'business')
        self.assertEqual(self.profile.business_name, 'STRIDE Technologies Ltd')
        self.assertEqual(self.profile.business_category, 'Hardware & Connected Identity')
        self.assertTrue(bool(self.profile.slug))

        is_configured = bool(self.profile.slug and (self.profile.title or self.profile.business_name))
        self.assertTrue(is_configured)

    def test_business_onboarding_skipping_optional_fields(self):
        """Business onboarding with optional category and description skipped."""
        self.client.login(email=self.user.email, password=self.password)
        post_data = {
            'profile_type': 'business',
            'full_name': 'Representative Name',
            'business_name': 'Acme Global Ventures',
            'business_category': '',     # skipped
            'business_description': '',  # skipped
            'address': '',               # skipped
        }
        response = self.client.post(reverse('dashboard:onboarding'), post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.business_name, 'Acme Global Ventures')
        self.assertTrue(bool(self.profile.slug))
        is_configured = bool(self.profile.slug and (self.profile.title or self.profile.business_name))
        self.assertTrue(is_configured)

    def test_existing_profile_revisiting_onboarding_preserves_attributes(self):
        """An already configured profile can load onboarding and update without corrupting fields."""
        self.profile.title = 'VP Engineering'
        self.profile.bio = 'Architecting distributed systems.'
        self.profile.save()

        self.client.login(email=self.user.email, password=self.password)
        response = self.client.get(reverse('dashboard:onboarding'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VP Engineering')
        self.assertContains(response, 'Architecting distributed systems.')
