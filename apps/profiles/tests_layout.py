from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile, ProfileService, ProfileGalleryItem, ProfileTestimonial, SocialLink, CustomLink

User = get_user_model()

class ProfileAppLayoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="alex@novastudio.com",
            password="StrongPassword123!",
            first_name="Alex",
            last_name="Carter",
            is_email_verified=True
        )
        self.profile = Profile.objects.get(user=self.user)
        self.profile.full_name = "Alex Carter"
        self.profile.title = "Product Designer & Founder"
        self.profile.business_name = "Nova Studio"
        self.profile.bio = "I build digital products that people love."
        self.profile.phone = "+2348011223344"
        self.profile.whatsapp = "+2348011223344"
        self.profile.email = "alex@novastudio.com"
        self.profile.website_url = "https://novastudio.com"
        self.profile.location = "New York, USA"
        self.profile.skills_tags = "Design, Product, Tech"
        self.profile.languages = "English, Spanish, French"
        self.profile.stat_experience = "5+ Years"
        self.profile.stat_projects = "50+ Projects"
        self.profile.stat_followers = "10K+ Network"
        self.profile.cta_banner_text = "Let's build something great together."
        self.profile.save()

        # Add Service
        self.service = ProfileService.objects.create(
            profile=self.profile,
            title="Product Design",
            description="UI/UX, Brand & Product",
            icon="design",
            order=1
        )

        # Add Gallery Item
        self.gallery_item = ProfileGalleryItem.objects.create(
            profile=self.profile,
            title="Nova Studio Web",
            image_url="https://images.unsplash.com/photo-1498050108023-c5249f4df085",
            link_url="https://novastudio.com",
            order=1
        )

        # Add Testimonial
        self.testimonial = ProfileTestimonial.objects.create(
            profile=self.profile,
            client_name="Sarah Mitchell",
            client_title="Product Manager, Google",
            content="Alex is a true professional. Creative, reliable and a pleasure to work with.",
            rating=5,
            order=1
        )

        # Add Social Link
        self.social_link = SocialLink.objects.create(
            profile=self.profile,
            platform="linkedin",
            url="https://linkedin.com/in/alexcarter",
            display_label="LinkedIn"
        )

        # Add Custom Link
        self.custom_link = CustomLink.objects.create(
            profile=self.profile,
            title="Portfolio",
            url="https://alexcarter.design",
            icon="briefcase"
        )

    def test_public_profile_renders_app_layout_and_tabs(self):
        url = reverse('profiles:public_profile', kwargs={'slug': self.profile.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Identity
        self.assertContains(resp, "Alex Carter")
        self.assertContains(resp, "Product Designer &amp; Founder")
        self.assertContains(resp, "Nova Studio")
        self.assertContains(resp, "New York, USA")

        # Tabs
        self.assertContains(resp, "tab-about")
        self.assertContains(resp, "tab-links")
        self.assertContains(resp, "tab-gallery")
        self.assertContains(resp, "tab-more")

        # Skills and Languages
        self.assertContains(resp, "Design")
        self.assertContains(resp, "Product")
        self.assertContains(resp, "Tech")
        self.assertContains(resp, "English")
        self.assertContains(resp, "Spanish")

        # Services
        self.assertContains(resp, "Product Design")
        self.assertContains(resp, "UI/UX, Brand &amp; Product")

        # Gallery
        self.assertContains(resp, "Nova Studio Web")

        # Testimonials
        self.assertContains(resp, "Sarah Mitchell")
        self.assertContains(resp, "Product Manager, Google")
        self.assertContains(resp, "Alex is a true professional")

        # Links
        self.assertContains(resp, "LinkedIn")
        self.assertContains(resp, "Portfolio")

        # Action buttons
        self.assertContains(resp, "Save Contact")
        self.assertContains(resp, "Share")
        self.assertContains(resp, "WhatsApp")
        self.assertContains(resp, "Call")

    def test_dashboard_service_crud(self):
        self.client.force_login(self.user)
        add_url = reverse('dashboard:profile_service_add')
        resp = self.client.post(add_url, {
            'title': 'Consulting',
            'description': 'Strategy & Growth',
            'icon': 'consulting',
            'order': 2
        })
        self.assertEqual(resp.status_code, 302)
        new_srv = ProfileService.objects.filter(profile=self.profile, title='Consulting').first()
        self.assertIsNotNone(new_srv)

        # Delete
        del_url = reverse('dashboard:profile_service_delete', kwargs={'item_id': new_srv.id})
        del_resp = self.client.post(del_url)
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(ProfileService.objects.filter(id=new_srv.id).exists())

    def test_dashboard_gallery_crud(self):
        self.client.force_login(self.user)
        add_url = reverse('dashboard:profile_gallery_add')
        resp = self.client.post(add_url, {
            'title': 'App UI Redesign',
            'image_url': 'https://example.com/image.png',
            'link_url': 'https://example.com',
            'order': 2
        })
        self.assertEqual(resp.status_code, 302)
        item = ProfileGalleryItem.objects.filter(profile=self.profile, title='App UI Redesign').first()
        self.assertIsNotNone(item)

        # Delete
        del_url = reverse('dashboard:profile_gallery_delete', kwargs={'item_id': item.id})
        del_resp = self.client.post(del_url)
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(ProfileGalleryItem.objects.filter(id=item.id).exists())

    def test_dashboard_testimonial_crud(self):
        self.client.force_login(self.user)
        add_url = reverse('dashboard:profile_testimonial_add')
        resp = self.client.post(add_url, {
            'client_name': 'David Kim',
            'client_title': 'Founder, ScaleUp',
            'content': 'Incredible design work and strong communication. Highly recommended!',
            'rating': 5,
            'order': 2
        })
        self.assertEqual(resp.status_code, 302)
        test_obj = ProfileTestimonial.objects.filter(profile=self.profile, client_name='David Kim').first()
        self.assertIsNotNone(test_obj)

        # Delete
        del_url = reverse('dashboard:profile_testimonial_delete', kwargs={'item_id': test_obj.id})
        del_resp = self.client.post(del_url)
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(ProfileTestimonial.objects.filter(id=test_obj.id).exists())

    def test_dashboard_profile_edit_saves_new_fields(self):
        self.client.force_login(self.user)
        edit_url = reverse('dashboard:profile_edit')
        resp = self.client.post(edit_url, {
            'full_name': 'Alex Carter Updated',
            'title': 'Staff Product Designer',
            'bio': 'Updated bio pitch.',
            'phone': '+2348099887766',
            'whatsapp': '+2348099887766',
            'email': 'alex@novastudio.com',
            'website_url': 'https://novastudio.com',
            'location': 'San Francisco, CA',
            'address': '100 Market St',
            'business_name': 'Nova Labs',
            'business_category': 'Technology',
            'business_description': 'Innovation studio',
            'skills_tags': 'Fintech, Web3, AI',
            'languages': 'English, German',
            'stat_experience': '8+ Years',
            'stat_projects': '80+ Projects',
            'stat_followers': '25K+ Clients',
            'cta_banner_text': 'Open for advisory roles.',
            'is_search_indexed': True
        })
        self.assertEqual(resp.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.skills_tags, 'Fintech, Web3, AI')
        self.assertEqual(self.profile.languages, 'English, German')
        self.assertEqual(self.profile.stat_experience, '8+ Years')
        self.assertEqual(self.profile.cta_banner_text, 'Open for advisory roles.')

    def test_appearance_page_has_no_phone_simulator(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('dashboard:appearance'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'sim-phone-frame')
        self.assertNotContains(resp, 'Live Phone Simulator')
        self.assertNotContains(resp, 'sim-body')
        self.assertContains(resp, 'appearance-layout-container')

    def test_all_themes_render_public_profile_with_atmosphere(self):
        for theme_key, theme_label in Profile.THEME_CHOICES:
            self.profile.theme = theme_key
            self.profile.save()
            url = reverse('profiles:public_profile', kwargs={'slug': self.profile.slug})
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, f'data-theme="{theme_key}"')
            self.assertContains(resp, 'prf-theme-atmosphere')
            self.assertContains(resp, 'prf-aura-orb')
            self.assertContains(resp, 'prf-particle-dust')

