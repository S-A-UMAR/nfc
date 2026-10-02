"""
UZYRA Sitemap Configuration
Generates XML sitemaps for indexable public content only.
Private dashboards, admin, draft content, and private profiles are excluded.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.profiles.models import Profile
from apps.websites.models import Website


class StaticViewSitemap(Sitemap):
    """Public static marketing pages."""
    priority = 0.9
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return [
            "core:home",
            "core:about",
            "core:smart_card",
            "core:websites",
            "core:how_it_works",
            "core:pricing",
            "core:faq",
            "core:business",
            "core:contact",
        ]

    def location(self, item):
        return reverse(item)


class ProfileSitemap(Sitemap):
    """Public profiles that have opted into search indexing."""
    priority = 0.7
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return Profile.objects.filter(
            is_search_indexed=True,
            slug__isnull=False,
        ).exclude(slug="").select_related("user")

    def location(self, profile):
        return reverse("profiles:public_profile", kwargs={"slug": profile.slug})

    def lastmod(self, profile):
        return getattr(profile, "updated_at", None)


class WebsiteSitemap(Sitemap):
    """Published customer websites only (excludes drafts, unpublished, maintenance)."""
    priority = 0.6
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return Website.objects.filter(
            status=Website.STATUS_PUBLISHED,
            slug__isnull=False,
        ).exclude(slug="")

    def location(self, website):
        return reverse("public_website", kwargs={"slug": website.slug})

    def lastmod(self, website):
        return getattr(website, "updated_at", None)
