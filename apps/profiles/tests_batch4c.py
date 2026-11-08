"""
Phase 3D, Batch 4C: My Profile Redesign Tests
Covers:
1. My Profile page loads with status 200, 3-section structure markers, save bar and navigation
2. Personal profile displays personal fields (full_name, title, bio, profile_image)
3. Business profile displays business fields (business_name, business_category, business_description, business_logo)
4. Profile saves and persists core fields through single save action
5. Image uploads (profile_image and business_logo) work and persist with SimpleUploadedFile
6. Existing uploaded images are preserved when saving without new file uploads
7. Form validation errors display cleanly and retain entered data
8. Advanced fields (location, address, skills_tags, languages, stats, cta_banner, search indexing) persist correctly
9. Public profile reflects saved changes accurately
10. Sub-modules (Services, Portfolio Gallery, Testimonials) remain fully functional
"""
import io
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.profiles.models import (
    Profile,
    ProfileService,
    ProfileGalleryItem,
    ProfileTestimonial
)

User = get_user_model()


def get_test_image(filename="test_image.png", color="blue"):
    """Helper to generate a valid in-memory image for upload testing."""
    file_obj = io.BytesIO()
    img = Image.new("RGB", (32, 32), color=color)
    img.save(file_obj, format="PNG")
    file_obj.seek(0)
    return SimpleUploadedFile(
        name=filename,
        content=file_obj.read(),
        content_type="image/png"
    )


class Batch4CProfileRedesignTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='elena.vance@example.com',
            password='Password123!',
            first_name='Elena',
            last_name='Vance',
            is_email_verified=True
        )
        self.profile = self.user.profile
        self.profile.full_name = 'Elena Vance'
        self.profile.title = 'Senior Systems Architect'
        self.profile.bio = 'Specialist in distributed consensus and fault-tolerant architecture.'
        self.profile.phone = '+15551234567'
        self.profile.whatsapp = '+15551234567'
        self.profile.email = 'elena.vance@example.com'
        self.profile.website_url = 'https://elenavance.dev'
        self.profile.location = 'Seattle, WA'
        self.profile.address = '500 Pike St'
        self.profile.profile_type = 'personal'
        self.profile.save()

        self.client = Client()
        self.client.force_login(self.user)
        self.edit_url = reverse('dashboard:profile_edit')

    def test_1_my_profile_page_loads_200(self):
        """Test 1: My Profile page loads with status 200, contains 3 clear sections and required controls."""
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)

        # Header and explanation
        self.assertContains(response, 'My Profile')
        self.assertContains(response, 'Manage your digital identity')

        # 3 Structured Sections
        self.assertContains(response, '1. Basic Identity')
        self.assertContains(response, '2. Contact Details &amp; Direct Actions')
        self.assertContains(response, '3. Advanced &amp; Optional Features')

        # Mode switcher and required selectors for existing test compatibility
        self.assertContains(response, 'edit-mode-personal')
        self.assertContains(response, 'edit-mode-business')
        self.assertContains(response, 'profile-sticky-save-bar')
        self.assertContains(response, 'btn-copy-live-link')
        self.assertContains(response, 'prf-quick-nav')

    def test_2_personal_profile_displays_personal_fields(self):
        """Test 2: Personal profile displays personal fields (full_name, title, bio, profile_image)."""
        self.profile.profile_type = 'personal'
        self.profile.save()

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Elena Vance')
        self.assertContains(response, 'Senior Systems Architect')
        self.assertContains(response, 'Specialist in distributed consensus')
        self.assertContains(response, 'name="full_name"')
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="bio"')
        self.assertContains(response, 'name="profile_image"')

    def test_3_business_profile_displays_business_fields(self):
        """Test 3: Business profile displays business fields (business_name, business_category, description, logo)."""
        self.profile.profile_type = 'business'
        self.profile.business_name = 'Vance Engineering LLC'
        self.profile.business_category = 'Engineering & Cloud'
        self.profile.business_description = 'High reliability distributed infrastructure solutions.'
        self.profile.save()

        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Vance Engineering LLC')
        self.assertContains(response, 'Engineering &amp; Cloud')
        self.assertContains(response, 'High reliability distributed infrastructure solutions.')
        self.assertContains(response, 'name="business_name"')
        self.assertContains(response, 'name="business_category"')
        self.assertContains(response, 'name="business_description"')
        self.assertContains(response, 'name="business_logo"')

    def test_4_profile_saves_and_persists_core_fields(self):
        """Test 4: Profile saves and persists core fields through single save action."""
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Dr. Elena Vance',
            'title': 'Principal Systems Engineer',
            'bio': 'Designing resilient cloud kernels and distributed protocols.',
            'phone': '+15559876543',
            'whatsapp': '+15559876543',
            'email': 'elena.vance.work@example.com',
            'website_url': 'https://vance-systems.io',
        }
        response = self.client.post(self.edit_url, post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, 'Dr. Elena Vance')
        self.assertEqual(self.profile.title, 'Principal Systems Engineer')
        self.assertEqual(self.profile.bio, 'Designing resilient cloud kernels and distributed protocols.')
        self.assertEqual(self.profile.phone, '+15559876543')
        self.assertEqual(self.profile.whatsapp, '+15559876543')
        self.assertEqual(self.profile.email, 'elena.vance.work@example.com')
        self.assertEqual(self.profile.website_url, 'https://vance-systems.io')

    def test_5_image_upload_profile_image_and_business_logo(self):
        """Test 5: Image uploads (profile_image and business_logo) work and persist."""
        avatar = get_test_image('avatar.png', color='green')
        logo = get_test_image('logo.png', color='gold')

        post_data = {
            'profile_type': 'business',
            'full_name': 'Elena Vance',
            'title': 'Chief Architect',
            'business_name': 'Vance Systems',
            'profile_image': avatar,
            'business_logo': logo,
        }
        response = self.client.post(self.edit_url, post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertTrue(bool(self.profile.profile_image))
        self.assertTrue(bool(self.profile.business_logo))
        self.assertIn('avatar', self.profile.profile_image.name)
        self.assertIn('logo', self.profile.business_logo.name)

    def test_6_existing_images_preserved_on_save(self):
        """Test 6: Existing uploaded images are preserved when saving without new file uploads."""
        avatar = get_test_image('avatar_initial.png', color='purple')
        self.profile.profile_image = avatar
        self.profile.save()

        initial_image_name = self.profile.profile_image.name
        self.assertTrue(bool(initial_image_name))

        # Save again with text changes only (no files uploaded)
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Elena Vance (Updated)',
            'title': 'Senior Systems Architect',
            'bio': 'Updated bio text without uploading new image.',
        }
        response = self.client.post(self.edit_url, post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, 'Elena Vance (Updated)')
        self.assertEqual(self.profile.profile_image.name, initial_image_name)

    def test_7_form_errors_display_properly(self):
        """Test 7: Form errors display properly and retain entered data on invalid input."""
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Valid Name',
            'website_url': 'invalid-url-without-scheme',
            'email': 'invalid-email-address',
        }
        response = self.client.post(self.edit_url, post_data)
        # Form error renders page with 200
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please correct the issues highlighted below')
        # Check input value retained
        self.assertContains(response, 'Valid Name')
        self.assertContains(response, 'invalid-url-without-scheme')

    def test_8_advanced_fields_persist_correctly(self):
        """Test 8: Advanced fields persist correctly in database."""
        post_data = {
            'profile_type': 'personal',
            'full_name': 'Elena Vance',
            'location': 'Bellevue, WA',
            'address': '108th Ave NE, Suite 400',
            'skills_tags': 'Rust, Distributed Systems, Raft, Kubernetes',
            'languages': 'English, French, Japanese',
            'stat_experience': '12+ Years',
            'stat_projects': '45+ Clusters',
            'stat_followers': '15K+ Developers',
            'cta_banner_text': 'Available for enterprise architecture consultations.',
            'is_search_indexed': True,
        }
        response = self.client.post(self.edit_url, post_data)
        self.assertEqual(response.status_code, 302)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.location, 'Bellevue, WA')
        self.assertEqual(self.profile.address, '108th Ave NE, Suite 400')
        self.assertEqual(self.profile.skills_tags, 'Rust, Distributed Systems, Raft, Kubernetes')
        self.assertEqual(self.profile.languages, 'English, French, Japanese')
        self.assertEqual(self.profile.stat_experience, '12+ Years')
        self.assertEqual(self.profile.stat_projects, '45+ Clusters')
        self.assertEqual(self.profile.stat_followers, '15K+ Developers')
        self.assertEqual(self.profile.cta_banner_text, 'Available for enterprise architecture consultations.')
        self.assertTrue(self.profile.is_search_indexed)

    def test_9_public_profile_reflects_saved_changes(self):
        """Test 9: Public profile reflects saved changes."""
        self.profile.full_name = 'Elena Vance, Ph.D.'
        self.profile.title = 'VP of Infrastructure'
        self.profile.bio = 'Leading cloud distributed systems.'
        self.profile.location = 'Seattle, Washington'
        self.profile.skills_tags = 'Cloud, Security, High-Availability'
        self.profile.save()

        public_url = reverse('profiles:public_profile', kwargs={'slug': self.profile.slug})
        response = self.client.get(public_url)
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Elena Vance, Ph.D.')
        self.assertContains(response, 'VP of Infrastructure')
        self.assertContains(response, 'Leading cloud distributed systems.')
        self.assertContains(response, 'Seattle, Washington')

    def test_10_submodules_services_gallery_testimonials_functional(self):
        """Test 10: Sub-modules (Services, Portfolio Gallery, Testimonials) remain fully functional."""
        # 1. Add Service
        service_url = reverse('dashboard:profile_service_add')
        resp = self.client.post(service_url, {
            'title': 'Consensus Consulting',
            'description': 'Architecture design for Raft & Paxos protocols.',
            'icon': 'code',
            'order': 1,
        })
        self.assertEqual(resp.status_code, 302)
        service = ProfileService.objects.filter(profile=self.profile, title='Consensus Consulting').first()
        self.assertIsNotNone(service)

        # 2. Add Gallery Item
        gallery_url = reverse('dashboard:profile_gallery_add')
        resp = self.client.post(gallery_url, {
            'title': 'Enterprise Cluster Topology',
            'image_url': 'https://images.unsplash.com/photo-1558494949-ef010cbdcc31',
            'link_url': 'https://vance-systems.io/case-study',
            'order': 1,
        })
        self.assertEqual(resp.status_code, 302)
        gallery_item = ProfileGalleryItem.objects.filter(profile=self.profile, title='Enterprise Cluster Topology').first()
        self.assertIsNotNone(gallery_item)

        # 3. Add Testimonial
        testimonial_url = reverse('dashboard:profile_testimonial_add')
        resp = self.client.post(testimonial_url, {
            'client_name': 'Marcus Vance',
            'client_title': 'CTO, Global FinTech',
            'content': 'Elena transformed our core transaction processing latency by 80%.',
            'rating': 5,
            'order': 1,
        })
        self.assertEqual(resp.status_code, 302)
        testimonial = ProfileTestimonial.objects.filter(profile=self.profile, client_name='Marcus Vance').first()
        self.assertIsNotNone(testimonial)

        # 4. Verify edit page displays all three sub-modules
        edit_resp = self.client.get(self.edit_url)
        self.assertEqual(edit_resp.status_code, 200)
        self.assertContains(edit_resp, 'Consensus Consulting')
        self.assertContains(edit_resp, 'Enterprise Cluster Topology')
        self.assertContains(edit_resp, 'Marcus Vance')
        self.assertContains(edit_resp, 'modal-add-service')
        self.assertContains(edit_resp, 'modal-add-gallery')
        self.assertContains(edit_resp, 'modal-add-testimonial')
