from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile, SocialLink, CustomLink

User = get_user_model()

class Phase3ProfileTests(TestCase):
    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()
        self.profile_url = reverse('dashboard:profile_edit')
        
        # User A
        self.user_a = User.objects.create_user(
            email='usera@example.com',
            password='Password123!',
            first_name='Alice',
            last_name='Smith'
        )
        
        # User B
        self.user_b = User.objects.create_user(
            email='userb@example.com',
            password='Password123!',
            first_name='Bob',
            last_name='Jones'
        )

    def test_1_user_creation_auto_creates_profile(self):
        """TEST 1: Confirm creating a user automatically provisions a Profile."""
        self.assertIsNotNone(self.user_a.profile)
        self.assertEqual(self.user_a.profile.full_name, 'Alice Smith')
        self.assertTrue(Profile.objects.filter(user=self.user_a).exists())

    def test_2_edit_professional_title_and_verify_persistence(self):
        """TEST 2: Edit professional title, save, refresh page, confirm data remains."""
        self.client_a.force_login(self.user_a)
        
        post_data = {
            'full_name': 'Alice Smith',
            'title': 'Senior Managing Director & VP',
            'bio': 'Initial bio string',
            'email': 'usera@example.com',
            'profile_type': 'personal',
            'theme': 'graphite',
            'is_search_indexed': 'on'
        }
        
        response = self.client_a.post(self.profile_url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify saved in database
        self.user_a.profile.refresh_from_db()
        self.assertEqual(self.user_a.profile.title, 'Senior Managing Director & VP')
        
        # Refresh page (GET request) and confirm title rendered
        get_response = self.client_a.get(self.profile_url)
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'Senior Managing Director &amp; VP')

    def test_3_change_bio_and_verify_persistence(self):
        """TEST 3: Change the bio, save, refresh, confirm new bio appears."""
        self.client_a.force_login(self.user_a)
        
        post_data = {
            'full_name': 'Alice Smith',
            'title': 'Senior Managing Director & VP',
            'bio': 'Pioneering technology executive with over 15 years experience leading cross-functional engineering teams.',
            'email': 'usera@example.com',
            'profile_type': 'personal',
            'theme': 'graphite',
            'is_search_indexed': 'on'
        }
        
        response = self.client_a.post(self.profile_url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify saved in database
        self.user_a.profile.refresh_from_db()
        self.assertEqual(
            self.user_a.profile.bio,
            'Pioneering technology executive with over 15 years experience leading cross-functional engineering teams.'
        )
        
        # Refresh page and confirm rendered
        get_response = self.client_a.get(self.profile_url)
        self.assertContains(get_response, 'Pioneering technology executive with over 15 years experience')

    def test_4_logout_and_login_preserves_profile_data(self):
        """TEST 4: Log out and log back in, confirm saved profile data remains."""
        # 1. Login & Save data
        self.client_a.force_login(self.user_a)
        post_data = {
            'full_name': 'Alice Smith',
            'title': 'Chief Technology Officer',
            'bio': 'Persistent profile data test bio.',
            'business_name': 'A-Tech Solutions Ltd',
            'email': 'usera@example.com',
            'profile_type': 'business',
            'theme': 'graphite',
            'is_search_indexed': 'on'
        }
        self.client_a.post(self.profile_url, post_data, follow=True)
        
        # 2. Log out
        self.client_a.get(reverse('accounts:logout'))
        self.assertNotIn('_auth_user_id', self.client_a.session)
        
        # 3. Log back in
        self.client_a.post(reverse('accounts:login'), {
            'username': 'usera@example.com',
            'password': 'Password123!'
        })
        self.assertIn('_auth_user_id', self.client_a.session)
        
        # 4. View profile dashboard and confirm saved data remains
        response = self.client_a.get(self.profile_url)
        self.assertContains(response, 'Chief Technology Officer')
        self.assertContains(response, 'Persistent profile data test bio.')
        self.assertContains(response, 'A-Tech Solutions Ltd')

    def test_5_user_a_cannot_edit_user_b_profile(self):
        """TEST 5: Confirm User A cannot edit User B's profile."""
        # Login User A
        self.client_a.force_login(self.user_a)
        
        # User A posts profile update to /dashboard/profile/
        post_data = {
            'full_name': 'Attempted Hacked Name',
            'title': 'Hacker Title',
            'email': 'hacked@example.com',
            'profile_type': 'personal',
            'theme': 'graphite'
        }
        self.client_a.post(self.profile_url, post_data)
        
        # Verify User A's profile was updated, but User B's profile was UNTOUCHED
        self.user_a.profile.refresh_from_db()
        self.user_b.profile.refresh_from_db()
        
        self.assertEqual(self.user_a.profile.full_name, 'Attempted Hacked Name')
        self.assertEqual(self.user_b.profile.full_name, 'Bob Jones')
        self.assertNotEqual(self.user_b.profile.full_name, 'Attempted Hacked Name')


class Phase4LinksTests(TestCase):
    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()
        self.links_url = reverse('dashboard:links_manage')
        
        self.user_a = User.objects.create_user(
            email='linkuser_a@example.com',
            password='Password123!',
            first_name='LinkUser',
            last_name='A'
        )
        self.user_b = User.objects.create_user(
            email='linkuser_b@example.com',
            password='Password123!',
            first_name='LinkUser',
            last_name='B'
        )
        self.profile_a = self.user_a.profile
        self.profile_b = self.user_b.profile

    def test_social_links_crud_and_persistence(self):
        """Phase 4 Test: Create 3 social links, refresh, logout/login, edit, toggle, delete."""
        self.client_a.force_login(self.user_a)
        
        # 1. Create 3 Social Links
        s1 = self.client_a.post(reverse('dashboard:add_social_link'), {'platform': 'instagram', 'url': 'https://instagram.com/user_a'})
        s2 = self.client_a.post(reverse('dashboard:add_social_link'), {'platform': 'linkedin', 'url': 'https://linkedin.com/in/user_a'})
        s3 = self.client_a.post(reverse('dashboard:add_social_link'), {'platform': 'x_twitter', 'url': 'https://x.com/user_a'})
        
        self.assertEqual(self.profile_a.social_links.count(), 3)
        
        # 2. Refresh page & confirm rendered
        resp_refresh = self.client_a.get(self.links_url)
        self.assertContains(resp_refresh, 'https://instagram.com/user_a')
        self.assertContains(resp_refresh, 'https://linkedin.com/in/user_a')
        self.assertContains(resp_refresh, 'https://x.com/user_a')
        
        # 3. Log out and Log in — confirm persistence
        self.client_a.get(reverse('accounts:logout'))
        self.client_a.post(reverse('accounts:login'), {'username': 'linkuser_a@example.com', 'password': 'Password123!'})
        resp_relogin = self.client_a.get(self.links_url)
        self.assertContains(resp_relogin, 'https://instagram.com/user_a')
        
        # 4. Edit a social link
        link1 = self.profile_a.social_links.get(platform='instagram')
        self.client_a.post(reverse('dashboard:edit_social_link', kwargs={'link_id': link1.id}), {
            'platform': 'instagram',
            'url': 'https://instagram.com/user_a_updated',
            'display_label': 'My Official IG'
        })
        link1.refresh_from_db()
        self.assertEqual(link1.url, 'https://instagram.com/user_a_updated')
        
        # 5. Toggle active status (Disable / Enable)
        self.client_a.post(reverse('dashboard:toggle_social_link', kwargs={'link_id': link1.id}))
        link1.refresh_from_db()
        self.assertFalse(link1.is_active)
        
        # 6. Delete a social link
        self.client_a.post(reverse('dashboard:delete_social_link', kwargs={'link_id': link1.id}))
        self.assertEqual(self.profile_a.social_links.count(), 2)

    def test_custom_links_crud_and_persistence(self):
        """Phase 4 Test: Create 3 custom links, refresh, logout/login, edit, toggle, delete."""
        self.client_a.force_login(self.user_a)
        
        # 1. Create 3 Custom Links
        c1 = self.client_a.post(reverse('dashboard:add_custom_link'), {'title': 'View My Website', 'url': 'https://mywebsite.com', 'icon': 'globe'})
        c2 = self.client_a.post(reverse('dashboard:add_custom_link'), {'title': 'Book an Appointment', 'url': 'https://calendly.com/user_a', 'icon': 'calendar'})
        c3 = self.client_a.post(reverse('dashboard:add_custom_link'), {'title': 'Download My CV', 'url': 'https://mywebsite.com/cv.pdf', 'icon': 'download'})
        
        self.assertEqual(self.profile_a.custom_links.count(), 3)
        
        # 2. Refresh page & confirm rendered
        resp_refresh = self.client_a.get(self.links_url)
        self.assertContains(resp_refresh, 'View My Website')
        self.assertContains(resp_refresh, 'Book an Appointment')
        self.assertContains(resp_refresh, 'Download My CV')
        
        # 3. Log out and Log in — confirm persistence
        self.client_a.get(reverse('accounts:logout'))
        self.client_a.post(reverse('accounts:login'), {'username': 'linkuser_a@example.com', 'password': 'Password123!'})
        resp_relogin = self.client_a.get(self.links_url)
        self.assertContains(resp_relogin, 'View My Website')
        
        # 4. Edit a custom link
        link1 = self.profile_a.custom_links.get(title='View My Website')
        self.client_a.post(reverse('dashboard:edit_custom_link', kwargs={'link_id': link1.id}), {
            'title': 'Explore My Portfolio',
            'url': 'https://portfolio.mywebsite.com',
            'icon': 'star'
        })
        link1.refresh_from_db()
        self.assertEqual(link1.title, 'Explore My Portfolio')
        self.assertEqual(link1.url, 'https://portfolio.mywebsite.com')
        
        # 5. Toggle active status
        self.client_a.post(reverse('dashboard:toggle_custom_link', kwargs={'link_id': link1.id}))
        link1.refresh_from_db()
        self.assertFalse(link1.is_active)
        
        # 6. Delete a custom link
        self.client_a.post(reverse('dashboard:delete_custom_link', kwargs={'link_id': link1.id}))
        self.assertEqual(self.profile_a.custom_links.count(), 2)

    def test_user_isolation_security_on_links(self):
        """Security Guard: User B cannot edit or delete User A's links."""
        self.client_a.force_login(self.user_a)
        self.client_a.post(reverse('dashboard:add_social_link'), {'platform': 'instagram', 'url': 'https://instagram.com/user_a'})
        link_a = self.profile_a.social_links.first()
        
        # User B attempts to delete User A's link
        self.client_b.force_login(self.user_b)
        response = self.client_b.post(reverse('dashboard:delete_social_link', kwargs={'link_id': link_a.id}))
        self.assertEqual(response.status_code, 404)
        
        # Link A still exists in DB
        self.assertTrue(SocialLink.objects.filter(id=link_a.id).exists())


class Phase5PublicProfileTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # User A
        self.user_a = User.objects.create_user(
            email='public_a@example.com',
            password='Password123!',
            first_name='Public',
            last_name='UserA'
        )
        self.profile_a = self.user_a.profile
        self.profile_a.title = 'VP of Digital Strategy'
        self.profile_a.bio = 'Pioneering physical-digital identity systems.'
        self.profile_a.whatsapp = '+2348011112222'
        self.profile_a.phone = '+2348011112222'
        self.profile_a.business_name = 'Identity Corp'
        self.profile_a.save()
        
        # User B
        self.user_b = User.objects.create_user(
            email='public_b@example.com',
            password='Password123!',
            first_name='Public',
            last_name='UserB'
        )
        self.profile_b = self.user_b.profile
        self.profile_b.title = 'Head of Hardware Engineering'
        self.profile_b.bio = 'NFC micro-chip Specialist.'
        self.profile_b.business_name = 'Silicon Systems'
        self.profile_b.save()

    def test_1_public_profile_displays_real_db_data(self):
        """TEST 1: Public profile renders real profile info, Instagram, WhatsApp, custom link."""
        SocialLink.objects.create(profile=self.profile_a, platform='instagram', url='https://instagram.com/public_a')
        CustomLink.objects.create(profile=self.profile_a, title='Visit Official Website', url='https://identcorp.com', icon='globe')
        
        url_a = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        response = self.client.get(url_a)
        self.assertEqual(response.status_code, 200)
        
        self.assertContains(response, 'Public UserA')
        self.assertContains(response, 'VP of Digital Strategy')
        self.assertContains(response, 'Pioneering physical-digital identity systems.')
        self.assertContains(response, 'Identity Corp')
        self.assertContains(response, 'https://wa.me/2348011112222')
        self.assertContains(response, 'https://instagram.com/public_a')
        self.assertContains(response, 'Visit Official Website')

    def test_2_profile_update_reflects_immediately_on_public_page(self):
        """TEST 2: Changing profile info immediately updates public profile page."""
        url_a = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        
        # Update title & bio in DB
        self.profile_a.title = 'Chief Executive Officer & Founder'
        self.profile_a.bio = 'Updated executive headline bio.'
        self.profile_a.save()
        
        response = self.client.get(url_a)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chief Executive Officer &amp; Founder')
        self.assertContains(response, 'Updated executive headline bio.')

    def test_3_disabled_social_link_disappears_from_public_page(self):
        """TEST 3: Disabling a social link removes it from public profile view."""
        link = SocialLink.objects.create(profile=self.profile_a, platform='instagram', url='https://instagram.com/public_a', is_active=True)
        url_a = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        
        # Verify rendered when active
        resp1 = self.client.get(url_a)
        self.assertContains(resp1, 'https://instagram.com/public_a')
        
        # Disable link in DB
        link.is_active = False
        link.save()
        
        # Verify hidden when disabled
        resp2 = self.client.get(url_a)
        self.assertNotContains(resp2, 'https://instagram.com/public_a')

    def test_4_deleted_custom_link_disappears_from_public_page(self):
        """TEST 4: Deleting a custom link removes it from public profile view."""
        c_link = CustomLink.objects.create(profile=self.profile_a, title='Temporary Catalogue', url='https://identcorp.com/cat.pdf')
        url_a = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        
        resp1 = self.client.get(url_a)
        self.assertContains(resp1, 'Temporary Catalogue')
        
        # Delete from DB
        c_link.delete()
        
        resp2 = self.client.get(url_a)
        self.assertNotContains(resp2, 'Temporary Catalogue')

    def test_5_user_isolation_between_public_profiles(self):
        """TEST 5: /u/user-a/ does not display User B info, and /u/user-b/ displays User B info."""
        url_a = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        url_b = reverse('profiles:public_profile', kwargs={'slug': self.profile_b.slug})
        
        resp_a = self.client.get(url_a)
        self.assertContains(resp_a, 'VP of Digital Strategy')
        self.assertNotContains(resp_a, 'Head of Hardware Engineering')
        
        resp_b = self.client.get(url_b)
        self.assertContains(resp_b, 'Head of Hardware Engineering')
        self.assertNotContains(resp_b, 'VP of Digital Strategy')
