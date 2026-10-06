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


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE CUSTOMIZATION V2 TESTS
# ─────────────────────────────────────────────────────────────────────────────

class ProfileCustomizationV2Tests(TestCase):
    """
    Tests for the UZYRA Profile Customization V2 system.
    Covers: model defaults, appearance save, IDOR, all themes render,
    all layouts render, analytics still fires, type/layout/theme persistence.
    """

    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()

        self.user_a = User.objects.create_user(
            email='appear_a@example.com',
            password='Password123!',
            first_name='Appear',
            last_name='UserA'
        )
        self.user_b = User.objects.create_user(
            email='appear_b@example.com',
            password='Password123!',
            first_name='Appear',
            last_name='UserB'
        )
        self.profile_a = self.user_a.profile
        self.profile_b = self.user_b.profile

        self.appearance_url = reverse('dashboard:appearance')

    # ── 1. Model defaults ───────────────────────────────────────────────────

    def test_new_profile_defaults_to_graphite_classic_personal(self):
        """New profiles should default to graphite theme, classic layout, personal type."""
        self.assertEqual(self.profile_a.theme, 'graphite')
        self.assertEqual(self.profile_a.profile_layout, 'classic')
        self.assertEqual(self.profile_a.profile_type, 'personal')

    # ── 2. Appearance dashboard access ──────────────────────────────────────

    def test_appearance_page_requires_login(self):
        """Unauthenticated users are redirected away from /dashboard/appearance/."""
        response = self.client.get(self.appearance_url)
        self.assertNotEqual(response.status_code, 200)
        self.assertIn(response.status_code, [301, 302])

    def test_appearance_page_loads_for_authenticated_user(self):
        """Authenticated user can load the appearance page."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profile Appearance')
        self.assertContains(response, 'profile_type')
        self.assertContains(response, 'profile_layout')
        self.assertContains(response, 'theme')

    def test_appearance_page_shows_all_personal_themes(self):
        """All 8 personal theme keys appear in the appearance template."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        for key in ['graphite', 'midnight', 'ocean', 'violet', 'emerald', 'rose', 'arctic', 'sand']:
            self.assertContains(response, key, msg_prefix=f"Missing personal theme: {key}")

    def test_appearance_page_shows_all_business_themes(self):
        """All 7 business theme keys appear in the appearance template."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        for key in ['executive', 'navy', 'emerald_business', 'royal', 'burgundy', 'luxury', 'platinum']:
            self.assertContains(response, key, msg_prefix=f"Missing business theme: {key}")

    def test_appearance_page_shows_all_personal_layouts(self):
        """All 5 personal layout keys appear in the appearance template."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        for key in ['classic', 'centered', 'minimal_layout', 'social', 'card']:
            self.assertContains(response, key, msg_prefix=f"Missing personal layout: {key}")

    def test_appearance_page_shows_all_business_layouts(self):
        """All 4 business layout keys appear in the appearance template."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        for key in ['executive_layout', 'brand_header', 'business_card', 'business_catalog']:
            self.assertContains(response, key, msg_prefix=f"Missing business layout: {key}")

    # ── 3. Appearance save (real DB persistence) ────────────────────────────

    def test_save_personal_ocean_centered_persists_to_db(self):
        """POST personal/ocean/centered → saves to database."""
        self.client_a.force_login(self.user_a)
        resp = self.client_a.post(self.appearance_url, {
            'profile_type': 'personal',
            'theme': 'ocean',
            'profile_layout': 'centered',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.profile_type, 'personal')
        self.assertEqual(self.profile_a.theme, 'ocean')
        self.assertEqual(self.profile_a.profile_layout, 'centered')

    def test_save_business_executive_layout_navy_persists_to_db(self):
        """POST business/navy/executive_layout → saves to database."""
        self.client_a.force_login(self.user_a)
        resp = self.client_a.post(self.appearance_url, {
            'profile_type': 'business',
            'theme': 'navy',
            'profile_layout': 'executive_layout',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.profile_type, 'business')
        self.assertEqual(self.profile_a.theme, 'navy')
        self.assertEqual(self.profile_a.profile_layout, 'executive_layout')

    def test_appearance_saves_all_personal_themes(self):
        """Every personal theme value is accepted and saved by the view."""
        self.client_a.force_login(self.user_a)
        for theme_key in ['graphite', 'midnight', 'ocean', 'violet', 'emerald', 'rose', 'arctic', 'sand']:
            resp = self.client_a.post(self.appearance_url, {
                'profile_type': 'personal',
                'theme': theme_key,
                'profile_layout': 'classic',
            })
            self.assertIn(resp.status_code, [200, 302], msg=f"Theme {theme_key} POST failed")
            self.profile_a.refresh_from_db()
            self.assertEqual(self.profile_a.theme, theme_key, msg=f"Theme {theme_key} not saved")

    def test_appearance_saves_all_business_themes(self):
        """Every business theme value is accepted and saved by the view."""
        self.client_a.force_login(self.user_a)
        for theme_key in ['executive', 'navy', 'emerald_business', 'royal', 'burgundy', 'luxury', 'platinum']:
            resp = self.client_a.post(self.appearance_url, {
                'profile_type': 'business',
                'theme': theme_key,
                'profile_layout': 'executive_layout',
            })
            self.assertIn(resp.status_code, [200, 302], msg=f"Theme {theme_key} POST failed")
            self.profile_a.refresh_from_db()
            self.assertEqual(self.profile_a.theme, theme_key, msg=f"Theme {theme_key} not saved")

    def test_appearance_saves_all_personal_layouts(self):
        """Every personal layout value is accepted and saved."""
        self.client_a.force_login(self.user_a)
        for layout in ['classic', 'centered', 'minimal_layout', 'social', 'card']:
            resp = self.client_a.post(self.appearance_url, {
                'profile_type': 'personal',
                'theme': 'graphite',
                'profile_layout': layout,
            })
            self.assertIn(resp.status_code, [200, 302], msg=f"Layout {layout} POST failed")
            self.profile_a.refresh_from_db()
            self.assertEqual(self.profile_a.profile_layout, layout, msg=f"Layout {layout} not saved")

    def test_appearance_saves_all_business_layouts(self):
        """Every business layout value is accepted and saved."""
        self.client_a.force_login(self.user_a)
        for layout in ['executive_layout', 'brand_header', 'business_card', 'business_catalog']:
            resp = self.client_a.post(self.appearance_url, {
                'profile_type': 'business',
                'theme': 'executive',
                'profile_layout': layout,
            })
            self.assertIn(resp.status_code, [200, 302], msg=f"Layout {layout} POST failed")
            self.profile_a.refresh_from_db()
            self.assertEqual(self.profile_a.profile_layout, layout, msg=f"Layout {layout} not saved")

    # ── 4. IDOR security ─────────────────────────────────────────────────────

    def test_idor_user_b_cannot_change_user_a_appearance(self):
        """
        User B POSTing to /dashboard/appearance/ must only affect User B's profile.
        User A's profile must remain unchanged.
        """
        # Set user A's profile to a distinct state
        self.profile_a.theme = 'violet'
        self.profile_a.profile_layout = 'social'
        self.profile_a.profile_type = 'personal'
        self.profile_a.save()

        # User B logs in and saves their own appearance
        self.client_b.force_login(self.user_b)
        self.client_b.post(self.appearance_url, {
            'profile_type': 'business',
            'theme': 'navy',
            'profile_layout': 'executive_layout',
        })

        # User A's profile must be untouched
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.theme, 'violet')
        self.assertEqual(self.profile_a.profile_layout, 'social')
        self.assertEqual(self.profile_a.profile_type, 'personal')

        # User B's profile must be updated
        self.profile_b.refresh_from_db()
        self.assertEqual(self.profile_b.theme, 'navy')
        self.assertEqual(self.profile_b.profile_layout, 'executive_layout')
        self.assertEqual(self.profile_b.profile_type, 'business')

    def test_appearance_endpoint_ignores_other_profile_fields(self):
        """
        The appearance endpoint must NEVER save full_name, bio, phone or other
        non-appearance fields — even if they are submitted in the POST body.
        """
        self.profile_a.full_name = 'Appear UserA'
        self.profile_a.bio = 'Original bio.'
        self.profile_a.save()

        self.client_a.force_login(self.user_a)
        self.client_a.post(self.appearance_url, {
            'profile_type': 'personal',
            'theme': 'emerald',
            'profile_layout': 'centered',
            # Attacker injects extra fields
            'full_name': 'HACKED NAME',
            'bio': 'Injected bio.',
            'phone': '+9999999999',
        })

        self.profile_a.refresh_from_db()
        # Appearance fields saved correctly
        self.assertEqual(self.profile_a.theme, 'emerald')
        # Non-appearance fields must NOT be modified
        self.assertEqual(self.profile_a.full_name, 'Appear UserA')
        self.assertEqual(self.profile_a.bio, 'Original bio.')
        self.assertEqual(self.profile_a.phone, '')

    # ── 5. Public profile renders theme + layout data-attributes ────────────

    def test_public_profile_renders_theme_data_attribute(self):
        """Public profile template must emit data-theme with the saved value."""
        self.profile_a.theme = 'violet'
        self.profile_a.save()
        url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        response = Client().get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-theme="violet"')

    def test_public_profile_renders_layout_data_attribute(self):
        """Public profile template must emit data-layout with the saved value."""
        self.profile_a.profile_layout = 'centered'
        self.profile_a.save()
        url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        response = Client().get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-layout="centered"')

    def test_public_profile_default_graphite_classic(self):
        """Default profile should render data-theme=graphite, data-layout=classic."""
        url = reverse('profiles:public_profile', kwargs={'slug': self.profile_b.slug})
        response = Client().get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-theme="graphite"')
        self.assertContains(response, 'data-layout="classic"')

    def test_all_personal_themes_render_on_public_profile(self):
        """Every personal theme value produces a 200 on the public profile."""
        for theme_key in ['graphite', 'midnight', 'ocean', 'violet', 'emerald', 'rose', 'arctic', 'sand']:
            self.profile_a.theme = theme_key
            self.profile_a.save()
            url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
            response = Client().get(url)
            self.assertEqual(response.status_code, 200, msg=f"Theme {theme_key} caused non-200")
            self.assertContains(response, f'data-theme="{theme_key}"')

    def test_all_business_themes_render_on_public_profile(self):
        """Every business theme value produces a 200 on the public profile."""
        for theme_key in ['executive', 'navy', 'emerald_business', 'royal', 'burgundy', 'luxury', 'platinum']:
            self.profile_a.theme = theme_key
            self.profile_a.save()
            url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
            response = Client().get(url)
            self.assertEqual(response.status_code, 200, msg=f"Business theme {theme_key} caused non-200")
            self.assertContains(response, f'data-theme="{theme_key}"')

    def test_all_personal_layouts_render_on_public_profile(self):
        """Every personal layout value produces a 200 on the public profile."""
        for layout in ['classic', 'centered', 'minimal_layout', 'social', 'card']:
            self.profile_a.profile_layout = layout
            self.profile_a.save()
            url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
            response = Client().get(url)
            self.assertEqual(response.status_code, 200, msg=f"Layout {layout} caused non-200")
            self.assertContains(response, f'data-layout="{layout}"')

    def test_all_business_layouts_render_on_public_profile(self):
        """Every business layout value produces a 200 on the public profile."""
        for layout in ['executive_layout', 'brand_header', 'business_card', 'business_catalog']:
            self.profile_a.profile_layout = layout
            self.profile_a.save()
            url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
            response = Client().get(url)
            self.assertEqual(response.status_code, 200, msg=f"Layout {layout} caused non-200")
            self.assertContains(response, f'data-layout="{layout}"')

    # ── 6. Analytics still fires on public profile ───────────────────────────

    def test_analytics_event_created_on_public_profile_view_with_theme(self):
        """
        Loading a public profile with a non-default theme still creates an
        analytics TYPE_PROFILE_VIEW event — theme system must not break analytics.
        """
        from apps.analytics.models import AnalyticsEvent
        self.profile_a.theme = 'midnight'
        self.profile_a.profile_layout = 'social'
        self.profile_a.save()

        initial_count = AnalyticsEvent.objects.filter(
            profile=self.profile_a,
            event_type=AnalyticsEvent.TYPE_PROFILE_VIEW
        ).count()

        url = reverse('profiles:public_profile', kwargs={'slug': self.profile_a.slug})
        Client().get(url)

        final_count = AnalyticsEvent.objects.filter(
            profile=self.profile_a,
            event_type=AnalyticsEvent.TYPE_PROFILE_VIEW
        ).count()
        self.assertEqual(final_count, initial_count + 1)

    # ── 7. Persistence across logout/login ───────────────────────────────────

    def test_appearance_persists_after_logout_login(self):
        """Theme and layout survive user logout and re-login."""
        self.client_a.force_login(self.user_a)
        self.client_a.post(self.appearance_url, {
            'profile_type': 'personal',
            'theme': 'rose',
            'profile_layout': 'minimal_layout',
        })

        # Log out
        self.client_a.get(reverse('accounts:logout'))

        # Re-login
        self.client_a.post(reverse('accounts:login'), {
            'username': 'appear_a@example.com',
            'password': 'Password123!'
        })

        # Re-check from DB
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.theme, 'rose')
        self.assertEqual(self.profile_a.profile_layout, 'minimal_layout')

    # ── 8. Invalid theme/layout values are rejected ──────────────────────────

    def test_invalid_theme_value_not_saved(self):
        """An invalid theme value must not be saved (form validation rejects it)."""
        self.client_a.force_login(self.user_a)
        original_theme = self.profile_a.theme
        self.client_a.post(self.appearance_url, {
            'profile_type': 'personal',
            'theme': 'hacker_injection_theme',
            'profile_layout': 'classic',
        })
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.theme, original_theme)

    def test_invalid_layout_value_not_saved(self):
        """An invalid layout value must not be saved (form validation rejects it)."""
        self.client_a.force_login(self.user_a)
        original_layout = self.profile_a.profile_layout
        self.client_a.post(self.appearance_url, {
            'profile_type': 'personal',
            'theme': 'graphite',
            'profile_layout': 'xss_injection_layout',
        })
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.profile_layout, original_layout)

    # ── 9. Website Builder Coming Soon ───────────────────────────────────────

    def test_website_builder_shows_coming_soon_banner(self):
        """Website Builder is locked — accessing the URL redirects to dashboard overview."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(reverse('dashboard:website_manage'))
        # Locked with redirect — Coming Soon
        self.assertEqual(response.status_code, 302)
        # Follow redirect — lands on dashboard (still 200)
        response = self.client_a.get(reverse('dashboard:website_manage'), follow=True)
        self.assertEqual(response.status_code, 200)


    # ── 10. Mobile responsive — appearance page loads without error ───────────

    def test_appearance_page_contains_responsive_css_classes(self):
        """Appearance page should contain key CSS classes for responsive grid."""
        self.client_a.force_login(self.user_a)
        response = self.client_a.get(self.appearance_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'appearance-type-grid')
        self.assertContains(response, 'appearance-layout-grid')
        self.assertContains(response, 'appearance-themes-grid')
        self.assertContains(response, 'appearance-save-bar')
