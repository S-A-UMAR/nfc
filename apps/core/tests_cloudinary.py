"""
STRIDE Cloudinary Media Storage Regression Tests
=================================================
Verifies:
1. StrideMediaCloudinaryStorage cleans asset names and handles malformed DB references.
2. Clean image URLs are constructed with '/image/upload/' and proper CDN format.
3. Existing valid Cloudinary assets (e.g. starting with 'media/') are preserved without duplicate prefixes.
4. OpenGraph and Twitter image meta tags in public profiles handle both absolute CDN URLs and relative local URLs correctly.
5. MEDIA_URL in settings is safely configured as '/media/'.
"""

import os
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from django.template import Template, Context
from apps.core.storage import StrideMediaCloudinaryStorage


class StrideCloudinaryStorageTests(TestCase):
    """Unit tests for StrideMediaCloudinaryStorage backend."""

    def setUp(self):
        self.storage = StrideMediaCloudinaryStorage()

    def test_clean_asset_name_empty_and_none(self):
        """Empty and None asset names return empty string safely."""
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(''), '')
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(None), '')

    def test_clean_asset_name_clean_path(self):
        """Already clean relative paths are unchanged."""
        clean = 'profiles/avatars/clean_avatar.jpg'
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(clean), clean)

    def test_clean_asset_name_malformed_staging_reference(self):
        """Malformed reference with single slash after scheme and cloud name is stripped."""
        malformed = 'https:/res.cloudinary.com/drh8fjiwq/profiles/avatars/WhatsApp_Image_2026-11-19_at_23.32.37_ezr1vu'
        expected = 'profiles/avatars/WhatsApp_Image_2026-11-19_at_23.32.37_ezr1vu'
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(malformed), expected)

    def test_clean_asset_name_malformed_double_slash_reference(self):
        """Malformed reference with standard double slash is stripped."""
        malformed = 'https://res.cloudinary.com/drh8fjiwq/profiles/covers/cover_photo.png'
        expected = 'profiles/covers/cover_photo.png'
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(malformed), expected)

    def test_clean_asset_name_leading_slash_handled(self):
        """Leading slashes are stripped cleanly."""
        path = '/profiles/avatars/user.jpg'
        self.assertEqual(StrideMediaCloudinaryStorage.clean_asset_name(path), 'profiles/avatars/user.jpg')

    def test_url_construction_clean_asset(self):
        """Clean asset generates valid Cloudinary delivery URL with /image/upload/."""
        url = self.storage.url('profiles/avatars/avatar.jpg')
        self.assertIn('res.cloudinary.com', url)
        self.assertIn('/image/upload/', url)
        self.assertIn('profiles/avatars/avatar.jpg', url)
        self.assertNotIn('https://res.cloudinary.com/https:', url)
        self.assertNotIn('https:/res.cloudinary.com', url.replace('https://res.cloudinary.com', '', 1))

    def test_url_construction_malformed_reference_resolved(self):
        """Malformed database reference is cleaned and produces valid Cloudinary URL."""
        malformed = 'https:/res.cloudinary.com/drh8fjiwq/profiles/avatars/WhatsApp_Image_2026-11-19_at_23.32.37_ezr1vu'
        url = self.storage.url(malformed)
        self.assertIn('res.cloudinary.com', url)
        self.assertIn('/image/upload/', url)
        self.assertIn('WhatsApp_Image_2026-11-19_at_23.32.37_ezr1vu', url)
        # Verify no duplicate scheme or host in the URL path
        self.assertNotIn('https:/res.cloudinary.com', url.replace('https://res.cloudinary.com', '', 1))
        self.assertNotIn('https://res.cloudinary.com', url.replace('https://res.cloudinary.com', '', 1))

    def test_url_construction_existing_valid_cloudinary_image(self):
        """Existing valid Cloudinary asset from July is preserved without double 'media/'."""
        existing = 'media/avatars/ChatGPT_Image_Jul_23_2026_02_29_12_PM_era27q.png'
        url = self.storage.url(existing)
        self.assertIn('res.cloudinary.com', url)
        self.assertIn('/image/upload/', url)
        self.assertIn('media/avatars/ChatGPT_Image_Jul_23_2026_02_29_12_PM_era27q.png', url)
        self.assertNotIn('media/media/', url)

    def test_url_empty_or_none(self):
        """url() returns empty string when asset name is empty or None."""
        self.assertEqual(self.storage.url(''), '')
        self.assertEqual(self.storage.url(None), '')

    def test_settings_media_url_is_relative(self):
        """MEDIA_URL must be '/media/' to ensure django-cloudinary-storage operates correctly."""
        self.assertEqual(settings.MEDIA_URL, '/media/')


class CloudinaryTemplateTagMetaTests(TestCase):
    """Tests that OpenGraph and Twitter meta tags render correctly for both CDN and local URLs."""

    TEMPLATE_SNIPPET = """
    {% if profile.profile_image %}
      <meta property="og:image" content="{% if '://' in profile.profile_image.url %}{{ profile.profile_image.url }}{% else %}{{ request.scheme }}://{{ request.get_host }}{{ profile.profile_image.url }}{% endif %}">
      <meta name="twitter:image" content="{% if '://' in profile.profile_image.url %}{{ profile.profile_image.url }}{% else %}{{ request.scheme }}://{{ request.get_host }}{{ profile.profile_image.url }}{% endif %}">
    {% endif %}
    """

    def test_absolute_cloudinary_url_not_prepended(self):
        """Absolute Cloudinary CDN URL must not be prepended with request.get_host."""
        cdn_url = "https://res.cloudinary.com/drh8fjiwq/image/upload/v1/media/profiles/avatars/user.jpg"
        
        class DummyImage:
            url = cdn_url

        class DummyProfile:
            profile_image = DummyImage()

        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/', HTTP_HOST='nfc-staging.up.railway.app')

        template = Template(self.TEMPLATE_SNIPPET)
        context = Context({'profile': DummyProfile(), 'request': request})
        rendered = template.render(context)

        self.assertIn(f'content="{cdn_url}"', rendered)
        self.assertNotIn('https://nfc-staging.up.railway.apphttps://', rendered)

    def test_relative_local_url_properly_prepended(self):
        """Relative media URL (local development) must be prepended with request.get_host."""
        local_url = "/media/profiles/avatars/user.jpg"
        
        class DummyImage:
            url = local_url

        class DummyProfile:
            profile_image = DummyImage()

        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/', HTTP_HOST='nfc-staging.up.railway.app')

        template = Template(self.TEMPLATE_SNIPPET)
        context = Context({'profile': DummyProfile(), 'request': request})
        rendered = template.render(context)

        expected_url = "http://nfc-staging.up.railway.app/media/profiles/avatars/user.jpg"
        self.assertIn(f'content="{expected_url}"', rendered)


class GalleryImageStorageRegressionTests(TestCase):
    """
    Regression tests for ProfileGalleryItem:
    Upload -> Saved Reference -> Cloudinary URL Construction -> Template Rendering.
    """

    def setUp(self):
        self.storage = StrideMediaCloudinaryStorage()

    def test_gallery_image_url_construction(self):
        """Gallery item image path generates valid Cloudinary delivery URL with /image/upload/."""
        url = self.storage.url('profiles/gallery/project_1_mockup.png')
        self.assertIn('res.cloudinary.com', url)
        self.assertIn('/image/upload/', url)
        self.assertIn('media/profiles/gallery/project_1_mockup.png', url)
        self.assertNotIn('https://res.cloudinary.com/https:', url)

    def test_gallery_template_rendering_public_profile(self):
        """Gallery carousel in public profile renders clean Cloudinary URL without malformed paths."""
        gallery_snippet = """
        {% if gallery_items %}
          <div class="prf-gallery-carousel">
            {% for item in gallery_items %}
              {% if item.image %}
                <img src="{{ item.image.url }}" alt="{{ item.title|default:'Work Item' }}">
              {% endif %}
            {% endfor %}
          </div>
        {% endif %}
        """
        cdn_gallery_url = "https://res.cloudinary.com/drh8fjiwq/image/upload/v1/media/profiles/gallery/design_mockup.png"

        class DummyGalleryItem:
            title = "Design Mockup"
            class DummyFieldFile:
                url = cdn_gallery_url
            image = DummyFieldFile()

        template = Template(gallery_snippet)
        context = Context({'gallery_items': [DummyGalleryItem()]})
        rendered = template.render(context)

        self.assertIn(f'src="{cdn_gallery_url}"', rendered)
        self.assertNotIn('https:/res.cloudinary.com', rendered.replace('https://res.cloudinary.com', '', 1))

    def test_media_cleanup_protects_gallery_referenced_assets(self):
        """MediaCleanupService.is_asset_referenced returns True if asset is in use by gallery items."""
        from apps.core.services.media_cleanup_service import MediaCleanupService
        from apps.profiles.models import Profile, ProfileGalleryItem
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(email='gallery_tester@strideid.com', password='Password123!')
        profile = getattr(user, 'profile', None) or Profile.objects.filter(user=user).first()
        if not profile:
            profile = Profile.objects.create(user=user, full_name='Gallery Tester')

        # Create gallery item with mock image path
        asset_path = 'profiles/gallery/active_portfolio_piece.jpg'
        gallery_item = ProfileGalleryItem.objects.create(
            profile=profile,
            title='Portfolio Piece',
            image=asset_path
        )

        # Asset should be detected as in-use
        public_id = 'profiles/gallery/active_portfolio_piece'
        self.assertTrue(MediaCleanupService.is_asset_referenced(public_id))

        # Check with exclude_user_id for another user - should still be True
        self.assertTrue(MediaCleanupService.is_asset_referenced(public_id, exclude_user_id=99999))

        # Check with exclude_user_id for owner - should be False (safe to clean when deleting owner account)
        self.assertFalse(MediaCleanupService.is_asset_referenced(public_id, exclude_user_id=user.id))
