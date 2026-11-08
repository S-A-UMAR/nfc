"""
Tests for STRIDE Phase 3D, Batch 4A: Links & Socials UX Overhaul.
Covers:
- Links management view rendering and context (configured_platforms)
- Quick Add Social link creation with handle normalization (@handle -> https://platform.com/handle)
- Duplicate platform prevention (warning message, no duplicate entry created)
- Social link edit, toggle visibility, and delete
- Custom CTA button add, edit, and delete
- Direct Link Mode toggle (enable with destination, disable, validation)
"""

from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User
from apps.profiles.models import Profile, SocialLink, CustomLink


class Phase3DBatch4ALinksSocialsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='linksuser@example.com',
            password='TestPassword123!',
            first_name='Amina',
            last_name='Bello',
            is_email_verified=True
        )
        self.profile = self.user.profile
        self.profile.full_name = 'Amina Bello'
        self.profile.slug = 'amina-bello-links'
        self.profile.title = 'Brand Strategist'
        self.profile.save()
        self.client = Client()
        self.client.login(email='linksuser@example.com', password='TestPassword123!')

    def test_links_manage_view_renders_successfully(self):
        """Page renders with 200, contains configured_platforms in context and intro copy."""
        response = self.client.get(reverse('dashboard:links_manage'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('configured_platforms', response.context)
        self.assertContains(response, 'Links &amp; Socials')
        self.assertContains(response, 'Connect the places where people can find and contact you')
        self.assertContains(response, 'Advanced NFC Card Routing')

    def test_quick_add_social_with_full_url(self):
        """Adding social link with full https URL succeeds."""
        response = self.client.post(reverse('dashboard:add_social_link'), {
            'platform': 'instagram',
            'url': 'https://instagram.com/aminabello',
            'display_label': 'Instagram',
            'is_active': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(SocialLink.objects.filter(profile=self.profile, platform='instagram').exists())
        link = SocialLink.objects.get(profile=self.profile, platform='instagram')
        self.assertEqual(link.url, 'https://instagram.com/aminabello')

    def test_quick_add_social_with_handle_normalization(self):
        """Entering handle '@aminabello' normalizes to 'https://instagram.com/aminabello'."""
        response = self.client.post(reverse('dashboard:add_social_link'), {
            'platform': 'instagram',
            'url': '@aminabello',
            'display_label': 'Instagram',
            'is_active': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        link = SocialLink.objects.filter(profile=self.profile, platform='instagram').first()
        self.assertIsNotNone(link)
        self.assertEqual(link.url, 'https://instagram.com/aminabello')

    def test_duplicate_social_platform_prevention(self):
        """Attempting to add duplicate platform gives a warning and prevents duplicate."""
        SocialLink.objects.create(
            profile=self.profile,
            platform='linkedin',
            url='https://linkedin.com/in/aminabello',
            display_label='LinkedIn'
        )
        initial_count = SocialLink.objects.filter(profile=self.profile, platform='linkedin').count()
        self.assertEqual(initial_count, 1)

        # Attempt to add linkedin again
        response = self.client.post(reverse('dashboard:add_social_link'), {
            'platform': 'linkedin',
            'url': 'https://linkedin.com/in/aminabello-duplicate',
            'display_label': 'LinkedIn 2',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        final_count = SocialLink.objects.filter(profile=self.profile, platform='linkedin').count()
        self.assertEqual(final_count, 1)  # No duplicate created
        self.assertContains(response, 'already have a')

    def test_edit_social_link(self):
        """User can edit URL and label of existing social link."""
        link = SocialLink.objects.create(
            profile=self.profile,
            platform='x_twitter',
            url='https://x.com/amina_old',
            display_label='X (Twitter)'
        )
        response = self.client.post(reverse('dashboard:edit_social_link', args=[link.id]), {
            'platform': 'x_twitter',
            'url': 'https://x.com/amina_new',
            'display_label': 'X Profile',
            'is_active': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.url, 'https://x.com/amina_new')
        self.assertEqual(link.display_label, 'X Profile')

    def test_toggle_social_link_visibility(self):
        """User can toggle link active/inactive status."""
        link = SocialLink.objects.create(
            profile=self.profile,
            platform='youtube',
            url='https://youtube.com/@aminabello',
            display_label='YouTube',
            is_active=True
        )
        response = self.client.post(reverse('dashboard:toggle_social_link', args=[link.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        link.refresh_from_db()
        self.assertFalse(link.is_active)

    def test_delete_social_link(self):
        """User can delete an existing social link."""
        link = SocialLink.objects.create(
            profile=self.profile,
            platform='tiktok',
            url='https://tiktok.com/@aminabello',
            display_label='TikTok'
        )
        response = self.client.post(reverse('dashboard:delete_social_link', args=[link.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SocialLink.objects.filter(id=link.id).exists())

    def test_add_custom_cta_button(self):
        """User can add a custom CTA action button with icon."""
        response = self.client.post(reverse('dashboard:add_custom_link'), {
            'title': 'Book Strategy Call',
            'url': 'https://calendly.com/aminabello',
            'icon': 'calendar',
            'is_active': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        custom_link = CustomLink.objects.filter(profile=self.profile, title='Book Strategy Call').first()
        self.assertIsNotNone(custom_link)
        self.assertEqual(custom_link.url, 'https://calendly.com/aminabello')
        self.assertEqual(custom_link.icon, 'calendar')

    def test_edit_custom_cta_button(self):
        """User can edit an existing custom CTA button."""
        link = CustomLink.objects.create(
            profile=self.profile,
            title='Old Title',
            url='https://portfolio.example.com',
            icon='globe'
        )
        response = self.client.post(reverse('dashboard:edit_custom_link', args=[link.id]), {
            'title': 'View Portfolio & Case Studies',
            'url': 'https://portfolio.example.com/work',
            'icon': 'briefcase',
            'is_active': 'on'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.title, 'View Portfolio & Case Studies')
        self.assertEqual(link.url, 'https://portfolio.example.com/work')
        self.assertEqual(link.icon, 'briefcase')

    def test_delete_custom_cta_button(self):
        """User can delete a custom link."""
        link = CustomLink.objects.create(
            profile=self.profile,
            title='Delete Me',
            url='https://example.com/temp',
            icon='link'
        )
        response = self.client.post(reverse('dashboard:delete_custom_link', args=[link.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CustomLink.objects.filter(id=link.id).exists())

    def test_direct_link_mode_enable_and_disable(self):
        """Direct link mode can be enabled with destination and disabled cleanly."""
        # Enable direct link mode
        response = self.client.post(reverse('dashboard:toggle_direct_link'), {
            'direct_link_enabled': 'on',
            'direct_link_url': 'https://calendly.com/aminabello/30min'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.direct_link_enabled)
        self.assertEqual(self.profile.direct_link_url, 'https://calendly.com/aminabello/30min')

        # Disable direct link mode
        response = self.client.post(reverse('dashboard:toggle_direct_link'), {
            'direct_link_enabled': '',
            'direct_link_url': ''
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.direct_link_enabled)
