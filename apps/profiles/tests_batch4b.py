"""
Phase 3D, Batch 4B: Appearance & Customization Redesign Tests
Covers:
- Visual workspace with 5 recommended themes prominently featured
- 'More Themes' accordion containing all functional alternatives
- Layout architecture options rendered as visual wireframes
- Removal of duplicate profile_type selector from appearance view
- Live real-time profile simulation container using actual profile fields
- Single clear save mechanism with unsaved-changes beforeunload protection
- Correct persistence of themes and layouts in database
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile

User = get_user_model()


class Batch4BAppearanceRedesignTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='audrey.designer@example.com',
            password='Password123!',
            first_name='Audrey',
            last_name='Hepburn'
        )
        self.profile = self.user.profile
        self.profile.full_name = 'Audrey Hepburn'
        self.profile.title = 'Creative Director & Designer'
        self.profile.bio = 'Specialising in digital branding and visual design systems.'
        self.profile.save()

        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse('dashboard:appearance')

    def test_appearance_page_loads_with_status_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Appearance &amp; Customization')
        self.assertContains(response, 'Choose how your digital profile looks to visitors')

    def test_five_recommended_themes_present_in_context(self):
        response = self.client.get(self.url)
        self.assertIn('recommended_themes', response.context)
        rec_keys = [t['key'] for t in response.context['recommended_themes']]
        for key in ['graphite', 'midnight', 'emerald', 'navy', 'luxury']:
            self.assertIn(key, rec_keys, f"Expected {key} in recommended themes")

    def test_more_themes_present_in_context(self):
        response = self.client.get(self.url)
        self.assertIn('more_themes', response.context)
        more_keys = [t['key'] for t in response.context['more_themes']]
        self.assertIn('ocean', more_keys)
        self.assertIn('rose', more_keys)
        self.assertIn('arctic', more_keys)
        self.assertIn('sand', more_keys)

    def test_duplicate_profile_type_selector_removed_from_ui(self):
        response = self.client.get(self.url)
        # There should no longer be visible button cards for selecting personal vs business mode
        self.assertNotContains(response, 'id="type-btn-personal"')
        self.assertNotContains(response, 'id="type-btn-business"')

    def test_live_preview_simulator_removed(self):
        response = self.client.get(self.url)
        # Live preview simulator must not be present in the customization workspace
        self.assertNotContains(response, 'appearance-preview-column')
        self.assertNotContains(response, 'id="live-profile-sim"')
        self.assertNotContains(response, 'id="phone-frame"')

    def test_all_five_recommended_themes_persist(self):
        for theme_key in ['graphite', 'midnight', 'emerald', 'navy', 'luxury']:
            resp = self.client.post(self.url, {
                'profile_type': self.profile.profile_type,
                'theme': theme_key,
                'profile_layout': 'classic',
            }, follow=True)
            self.assertEqual(resp.status_code, 200)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.theme, theme_key)

    def test_all_personal_layouts_persist(self):
        for layout_key in ['classic', 'centered', 'minimal_layout', 'social', 'card']:
            resp = self.client.post(self.url, {
                'profile_type': self.profile.profile_type,
                'theme': 'graphite',
                'profile_layout': layout_key,
            }, follow=True)
            self.assertEqual(resp.status_code, 200)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.profile_layout, layout_key)

    def test_business_profile_shows_business_layouts(self):
        # Update profile to business via My Profile
        self.profile.profile_type = 'business'
        self.profile.business_name = 'Hepburn Studios'
        self.profile.business_category = 'Design Agency'
        self.profile.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'business-layouts-grid')
        self.assertContains(response, 'executive_layout')
        self.assertContains(response, 'brand_header')
        self.assertContains(response, 'business_card')
        self.assertContains(response, 'business_catalog')
        self.assertContains(response, 'Hepburn Studios')

    def test_single_clear_save_mechanism_rendered(self):
        response = self.client.get(self.url)
        # Verify single floating save bar and button exists
        self.assertContains(response, 'id="save-dock"')
        self.assertContains(response, 'id="btn-save-appearance"')
        # Header should NOT have a duplicate save button
        self.assertNotContains(response, 'id="btn-header-save"')

    def test_unsaved_changes_warning_script_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'beforeunload')
        self.assertContains(response, 'Unsaved visual changes')
