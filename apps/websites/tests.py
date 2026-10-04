from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Website, Service, Product
from apps.profiles.models import Profile

User = get_user_model()

class WebsiteBuilderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="builder@uzyra.com", password="password123")
        self.profile = self.user.profile
        
        self.other_user = User.objects.create_user(email="other@uzyra.com", password="password123")
        self.other_profile = self.other_user.profile

    def test_website_manage_empty_state_get(self):
        self.client.login(email="builder@uzyra.com", password="password123")
        response = self.client.get(reverse('dashboard:website_manage'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Website Created Yet")

    def test_create_website(self):
        self.client.login(email="builder@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:website_manage'), {'title': 'My New Website'})
        self.assertEqual(response.status_code, 302)
        
        website = Website.objects.get(user=self.user)
        self.assertEqual(website.title, 'My New Website')
        self.assertEqual(website.status, Website.STATUS_DRAFT)

    def test_update_website_settings(self):
        website = Website.objects.create(user=self.user, title="Initial", status=Website.STATUS_DRAFT)
        self.client.login(email="builder@uzyra.com", password="password123")
        
        response = self.client.post(reverse('dashboard:website_manage'), {
            'update_website': '1',
            'title': 'Updated Title',
            'slug': 'updated-slug',
            'template_choice': 'modern_business',
            'status': Website.STATUS_DRAFT,
            'primary_color': '#ff0000',
            'secondary_color': '#00ff00',
            'button_style': 'solid',
            'show_hero': True,
        })
        self.assertEqual(response.status_code, 302)
        website.refresh_from_db()
        self.assertEqual(website.title, 'Updated Title')
        self.assertEqual(website.slug, 'updated-slug')
        self.assertEqual(website.primary_color, '#ff0000')

    def test_website_publish_toggle(self):
        website = Website.objects.create(user=self.user, title="To Publish", status=Website.STATUS_DRAFT)
        self.client.login(email="builder@uzyra.com", password="password123")
        
        # Publish
        response = self.client.post(reverse('dashboard:website_publish', args=[website.id]))
        self.assertEqual(response.status_code, 302)
        website.refresh_from_db()
        self.assertEqual(website.status, Website.STATUS_PUBLISHED)
        
        # Unpublish
        response = self.client.post(reverse('dashboard:website_publish', args=[website.id]))
        self.assertEqual(response.status_code, 302)
        website.refresh_from_db()
        self.assertEqual(website.status, Website.STATUS_UNPUBLISHED)

    def test_public_website_view(self):
        website = Website.objects.create(user=self.user, title="Public Site", slug="public-site", status=Website.STATUS_PUBLISHED)
        
        response = self.client.get(reverse('public_website', args=[website.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Site")
        
    def test_public_website_unpublished(self):
        website = Website.objects.create(user=self.user, title="Private Site", slug="private-site", status=Website.STATUS_DRAFT)
        
        response = self.client.get(reverse('public_website', args=[website.slug]))
        self.assertEqual(response.status_code, 404)

    def test_preview_website_view(self):
        website = Website.objects.create(user=self.user, title="Preview Site", slug="preview-site", status=Website.STATUS_DRAFT)
        
        # Anonymous cannot preview
        response = self.client.get(reverse('preview_website', args=[website.slug]))
        self.assertNotEqual(response.status_code, 200)
        
        # Owner can preview
        self.client.login(email="builder@uzyra.com", password="password123")
        response = self.client.get(reverse('preview_website', args=[website.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PREVIEW MODE")
        self.assertContains(response, "Preview Site")

    def test_idor_protection_publish(self):
        website = Website.objects.create(user=self.user, title="Builder Site", status=Website.STATUS_DRAFT)
        
        # Other user tries to publish builder's site
        self.client.login(email="other@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:website_publish', args=[website.id]))
        self.assertEqual(response.status_code, 404)
        
        website.refresh_from_db()
        self.assertEqual(website.status, Website.STATUS_DRAFT)

    def test_service_crud(self):
        website = Website.objects.create(user=self.user, title="Site", status=Website.STATUS_DRAFT)
        self.client.login(email="builder@uzyra.com", password="password123")
        
        # Create
        response = self.client.post(reverse('dashboard:service_add', args=[website.id]), {
            'name': 'SEO Audit',
            'description': 'Deep dive',
            'price': '$500',
            'is_active': True,
            'display_order': 1
        })
        self.assertEqual(Service.objects.count(), 1)
        service = Service.objects.first()
        self.assertEqual(service.name, 'SEO Audit')
        
        # IDOR Delete
        self.client.login(email="other@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:service_delete', args=[service.id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Service.objects.count(), 1)
        
        # Owner Delete
        self.client.login(email="builder@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:service_delete', args=[service.id]))
        self.assertEqual(Service.objects.count(), 0)

    def test_service_edit_and_toggle(self):
        website = Website.objects.create(user=self.user, title="Site", status=Website.STATUS_DRAFT)
        service = Service.objects.create(website=website, name="Initial Name", price="100", is_active=True)
        self.client.login(email="builder@uzyra.com", password="password123")

        # Edit
        response = self.client.post(reverse('dashboard:service_edit', args=[service.id]), {
            'name': 'Updated Service',
            'price': '₦75,000',
            'description': 'Premium service',
            'is_active': True,
            'display_order': 2,
        })
        self.assertEqual(response.status_code, 302)
        service.refresh_from_db()
        self.assertEqual(service.name, 'Updated Service')
        self.assertEqual(service.price, '₦75,000')

        # Toggle Active
        response = self.client.post(reverse('dashboard:service_toggle', args=[service.id]))
        self.assertEqual(response.status_code, 302)
        service.refresh_from_db()
        self.assertFalse(service.is_active)

    def test_product_crud_and_toggle(self):
        website = Website.objects.create(user=self.user, title="Site", status=Website.STATUS_DRAFT)
        self.client.login(email="builder@uzyra.com", password="password123")

        # Create Product
        response = self.client.post(reverse('dashboard:product_add', args=[website.id]), {
            'name': 'Luxury Smart Card',
            'price': '₦35,000',
            'description': 'Matte black metal card',
            'is_active': True,
            'display_order': 1,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), 1)
        product = Product.objects.first()
        self.assertEqual(product.name, 'Luxury Smart Card')

        # Edit Product
        response = self.client.post(reverse('dashboard:product_edit', args=[product.id]), {
            'name': 'Gold Smart Card',
            'price': '₦50,000',
            'description': '24K gold plated',
            'is_active': True,
            'display_order': 1,
        })
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, 'Gold Smart Card')

        # Toggle Active
        response = self.client.post(reverse('dashboard:product_toggle', args=[product.id]))
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertFalse(product.is_active)

        # Delete Product IDOR defense
        self.client.login(email="other@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:product_delete', args=[product.id]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Product.objects.count(), 1)

        # Owner Delete Product
        self.client.login(email="builder@uzyra.com", password="password123")
        response = self.client.post(reverse('dashboard:product_delete', args=[product.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), 0)

    def test_all_templates_render_successfully(self):
        """Ensure all 4 template choices render properly without TemplateDoesNotExist."""
        self.client.login(email="builder@uzyra.com", password="password123")
        templates = ['modern_business', 'luxury_atelier', 'creator_portfolio', 'retail_showcase']

        for tmpl in templates:
            website = Website.objects.create(
                user=self.user,
                title=f"Site {tmpl}",
                slug=f"site-{tmpl}",
                template_choice=tmpl,
                status=Website.STATUS_PUBLISHED,
                headline=f"Headline {tmpl}",
                tagline=f"Tagline {tmpl}",
            )
            # Add a sample service and product
            Service.objects.create(website=website, name=f"Service for {tmpl}", price="₦10,000", is_active=True)
            Product.objects.create(website=website, name=f"Product for {tmpl}", price="₦20,000", is_active=True)

            # Public render
            resp = self.client.get(reverse('public_website', args=[website.slug]))
            self.assertEqual(resp.status_code, 200, f"Template {tmpl} failed public render")
            self.assertContains(resp, f"Site {tmpl}")
            self.assertContains(resp, f"Service for {tmpl}")
            self.assertContains(resp, f"Product for {tmpl}")

            # Preview render
            prev_resp = self.client.get(reverse('preview_website', args=[website.slug]))
            self.assertEqual(prev_resp.status_code, 200, f"Template {tmpl} failed preview render")
            self.assertContains(prev_resp, f"Site {tmpl}")

