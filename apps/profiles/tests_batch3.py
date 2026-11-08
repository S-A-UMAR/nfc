"""
STRIDE Phase 3C Batch 3 — Public Profile Tests
Tests for data integrity, personal/business distinction, vCard, QR, privacy, and direct-link mode.

NOTE: A Django signal auto-creates a Profile for every new User, so tests use
Profile.objects.filter(user=...).update(...) or get_and_update helpers rather
than Profile.objects.create().
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile, ProfileService

User = get_user_model()


def _make_user_with_profile(user_email, password="TestPass99!", **profile_kwargs):
    """Create a user and update the auto-created profile with the given kwargs."""
    user = User.objects.create_user(email=user_email, password=password, is_email_verified=True)
    Profile.objects.filter(user=user).update(**profile_kwargs)
    return user, Profile.objects.get(user=user)


class PublicProfilePersonalTests(TestCase):
    """Personal profile: renders correct fields, hides un-set fields."""

    def setUp(self):
        self.user, self.profile = _make_user_with_profile(
            "personal_b3@stride.id",
            full_name="Alice Smith",
            title="Product Designer",
            bio="I design user-centred digital products.",
            phone="+447900123456",
            email="alice@example.com",
            profile_type="personal",
            slug="alice-smith-b3",
            is_search_indexed=True,
        )
        self.url = reverse("profiles:public_profile", kwargs={"slug": self.profile.slug})
        self.client = Client()

    def test_profile_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_personal_name_in_hero(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Alice Smith")

    def test_personal_title_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Product Designer")

    def test_personal_bio_shown(self):
        response = self.client.get(self.url)
        self.assertContains(response, "I design user-centred digital products.")

    def test_no_fabricated_services_when_none_exist(self):
        """Profile with no services must NOT render fabricated default service cards."""
        response = self.client.get(self.url)
        body = response.content.decode()
        self.assertNotIn("Professional Services", body)
        self.assertNotIn("Consulting &amp; Advisory", body)

    def test_no_languages_heading_when_languages_empty(self):
        """Languages section must not appear when profile.languages is empty."""
        self.profile.languages = ""
        self.profile.save()
        response = self.client.get(self.url)
        # The Languages heading must not be in the response
        self.assertNotIn('<h2 class="prf-section-heading">Languages</h2>', response.content.decode())

    def test_languages_shown_when_set(self):
        self.profile.languages = "English, French"
        self.profile.save()
        response = self.client.get(self.url)
        body = response.content.decode()
        self.assertIn("Languages", body)
        self.assertIn("English", body)

    def test_stats_bar_hidden_when_defaults(self):
        """Stats bar must be hidden when all three stat fields are at their model defaults."""
        self.assertEqual(self.profile.stat_experience, "5+ Years")
        self.assertEqual(self.profile.stat_projects, "50+ Projects")
        self.assertEqual(self.profile.stat_followers, "10K+ Network")
        response = self.client.get(self.url)
        self.assertNotIn("prf-stats-bar", response.content.decode())

    def test_stats_bar_shown_when_customised(self):
        self.profile.stat_experience = "3 Years"
        self.profile.save()
        response = self.client.get(self.url)
        self.assertIn("prf-stats-bar", response.content.decode())
        self.assertContains(response, "3 Years")

    def test_services_shown_when_exist(self):
        ProfileService.objects.create(
            profile=self.profile,
            title="UX Research",
            description="User interviews and usability testing.",
            icon="briefcase",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "UX Research")
        self.assertContains(response, "What I Do")

    def test_about_heading_is_about_me(self):
        response = self.client.get(self.url)
        self.assertContains(response, "About Me")


class PublicProfileBusinessTests(TestCase):
    """Business profile: renders business fields with distinct layout."""

    def setUp(self):
        self.user, self.profile = _make_user_with_profile(
            "business_b3@stride.id",
            full_name="Khadija Usman",
            business_name="Khadija Logistics Ltd",
            business_description="Nationwide freight forwarding services.",
            business_category="Supply Chain & Logistics",
            address="42 Commercial Avenue, Lagos",
            phone="+2348039876543",
            email="biz@example.com",
            profile_type="business",
            slug="khadija-logistics-b3",
            is_search_indexed=True,
        )
        self.url = reverse("profiles:public_profile", kwargs={"slug": self.profile.slug})
        self.client = Client()

    def test_business_profile_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_business_name_in_hero(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Khadija Logistics Ltd")

    def test_business_category_chip_shown(self):
        response = self.client.get(self.url)
        body = response.content.decode()
        self.assertIn("prf-business-category", body)
        self.assertIn("Supply Chain", body)

    def test_business_description_in_about_tab(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Nationwide freight forwarding services.")

    def test_about_heading_includes_business_name(self):
        response = self.client.get(self.url)
        self.assertContains(response, "About Khadija Logistics Ltd")

    def test_address_shown_in_quicklist(self):
        response = self.client.get(self.url)
        self.assertContains(response, "42 Commercial Avenue, Lagos")

    def test_no_fabricated_services_for_business(self):
        response = self.client.get(self.url)
        body = response.content.decode()
        self.assertNotIn("Professional Services", body)

    def test_no_stats_bar_at_defaults(self):
        response = self.client.get(self.url)
        self.assertNotIn("prf-stats-bar", response.content.decode())

    def test_business_services_show_what_we_offer(self):
        ProfileService.objects.create(
            profile=self.profile,
            title="Freight Forwarding",
            description="End-to-end cargo management.",
            icon="briefcase",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "What We Offer")
        self.assertContains(response, "Freight Forwarding")


class VCardTests(TestCase):
    """vCard download: returns valid .vcf, distinguishes personal/business."""

    def setUp(self):
        self.user_p, self.personal = _make_user_with_profile(
            "vcard_personal_b3@stride.id",
            full_name="Bob Jones",
            title="Engineer",
            email="bob@example.com",
            phone="+447000000001",
            profile_type="personal",
            slug="bob-jones-b3",
        )
        self.user_b, self.business = _make_user_with_profile(
            "vcard_business_b3@stride.id",
            full_name="Business Owner",
            business_name="Acme Corp",
            email="info@acme.com",
            profile_type="business",
            slug="acme-corp-b3",
        )
        self.client = Client()

    def test_vcard_personal_returns_200(self):
        url = reverse("profiles:download_vcard", kwargs={"slug": self.personal.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_vcard_personal_content_type(self):
        url = reverse("profiles:download_vcard", kwargs={"slug": self.personal.slug})
        response = self.client.get(url)
        self.assertIn("text/vcard", response.get("Content-Type", ""))

    def test_vcard_personal_contains_fn(self):
        url = reverse("profiles:download_vcard", kwargs={"slug": self.personal.slug})
        response = self.client.get(url)
        body = response.content.decode()
        self.assertIn("FN:Bob Jones", body)

    def test_vcard_business_contains_org(self):
        url = reverse("profiles:download_vcard", kwargs={"slug": self.business.slug})
        response = self.client.get(url)
        body = response.content.decode()
        self.assertIn("ORG:Acme Corp", body)

    def test_vcard_personal_does_not_contain_business_org(self):
        url = reverse("profiles:download_vcard", kwargs={"slug": self.personal.slug})
        response = self.client.get(url)
        body = response.content.decode()
        self.assertNotIn("ORG:Acme Corp", body)


class QRCodeTests(TestCase):
    """QR code endpoint returns a PNG image."""

    def setUp(self):
        self.user, self.profile = _make_user_with_profile(
            "qr_b3@stride.id",
            full_name="QR Tester",
            profile_type="personal",
            slug="qr-tester-b3",
        )
        self.client = Client()

    def test_qr_returns_200(self):
        url = reverse("profiles:download_profile_qr", kwargs={"slug": self.profile.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_qr_content_type_is_png(self):
        url = reverse("profiles:download_profile_qr", kwargs={"slug": self.profile.slug})
        response = self.client.get(url)
        self.assertEqual(response.get("Content-Type"), "image/png")


class PrivacyTests(TestCase):
    """Private profile fields must not be exposed."""

    def setUp(self):
        self.user, self.profile = _make_user_with_profile(
            "private_b3@stride.id",
            full_name="Private Person",
            profile_type="personal",
            slug="private-person-b3",
            is_search_indexed=False,
        )
        self.client = Client()

    def test_private_profile_has_noindex_meta(self):
        url = reverse("profiles:public_profile", kwargs={"slug": self.profile.slug})
        response = self.client.get(url)
        self.assertContains(response, "noindex, nofollow")

    def test_public_profile_no_noindex_when_indexed(self):
        self.profile.is_search_indexed = True
        self.profile.save()
        url = reverse("profiles:public_profile", kwargs={"slug": self.profile.slug})
        response = self.client.get(url)
        body = response.content.decode()
        self.assertNotIn("noindex", body)


class DirectLinkModeTests(TestCase):
    """Direct link mode: non-owner redirected, owner sees full profile."""

    def setUp(self):
        self.user, self.profile = _make_user_with_profile(
            "dlm_owner_b3@stride.id",
            full_name="DLM Owner",
            profile_type="personal",
            slug="dlm-owner-b3",
            direct_link_enabled=True,
            direct_link_url="https://example.com/redirect",
        )
        self.url = reverse("profiles:public_profile", kwargs={"slug": self.profile.slug})
        self.client = Client()

    def test_non_owner_redirected_when_direct_link_active(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            "https://example.com/redirect",
            fetch_redirect_response=False,
        )

    def test_owner_sees_full_profile(self):
        self.client.login(email="dlm_owner_b3@stride.id", password="TestPass99!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DLM Owner")

    def test_preview_param_bypasses_redirect_for_non_owner(self):
        response = self.client.get(self.url + "?preview=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DLM Owner")
