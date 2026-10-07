from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile, CustomLink
from apps.cards.models import Card
from apps.orders.models import Order, ProductPackage
from apps.core.models import ContactMessage
from apps.core.admin import InquiryCategoryFilter, ContactMessageAdmin
from apps.analytics.models import AnalyticsEvent
from django.contrib.admin.sites import AdminSite

User = get_user_model()


class MockRequest:
    pass


class Phase2PrivacyAndDataRightsTests(TestCase):
    def setUp(self):
        self.password = 'SecurePassword123!'
        
        # Create User A
        self.user_a = User.objects.create_user(
            email='alice@example.com',
            password=self.password,
            first_name='Alice',
            last_name='Tester',
            phone='+2348011223344'
        )
        self.profile_a, _ = Profile.objects.get_or_create(
            user=self.user_a,
            defaults={'full_name': 'Alice Tester', 'title': 'Design Lead', 'bio': 'Original bio'}
        )
        
        # Create User B
        self.user_b = User.objects.create_user(
            email='bob@example.com',
            password=self.password,
            first_name='Bob',
            last_name='Adversary',
            phone='+2348099887766'
        )
        self.profile_b, _ = Profile.objects.get_or_create(
            user=self.user_b,
            defaults={'full_name': 'Bob Adversary'}
        )

        # Clients
        self.client_a = Client()
        self.client_a.login(email='alice@example.com', password=self.password)

        self.client_b = Client()
        self.client_b.login(email='bob@example.com', password=self.password)

        self.anon_client = Client()

    def test_authenticated_user_can_access_own_settings_and_data(self):
        """User A can access their own account details in settings."""
        url = reverse('dashboard:settings_view')
        response = self.client_a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')
        self.assertContains(response, 'alice@example.com')
        # Check that NDPA Privacy & Data Rights section is present
        self.assertContains(response, 'Privacy &amp; Data Rights')
        self.assertContains(response, 'NDPA 2023')
        self.assertContains(response, 'Export My Contact Card (.vcf)')
        self.assertContains(response, 'Account Deletion')

    def test_user_can_correct_personal_data_in_settings(self):
        """User A can update their personal information (Right to Rectification)."""
        url = reverse('dashboard:settings_view')
        response = self.client_a.post(url, {
            'update_account': '1',
            'first_name': 'Alicia',
            'last_name': 'Updated',
            'email': self.user_a.email,
            'phone': '+2348099999999'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.first_name, 'Alicia')
        self.assertEqual(self.user_a.last_name, 'Updated')
        self.assertEqual(self.user_a.phone, '+2348099999999')

    def test_user_can_correct_profile_data(self):
        """User A can update their public profile content."""
        url = reverse('dashboard:profile_edit')
        response = self.client_a.post(url, {
            'full_name': 'Alicia T.',
            'title': 'Senior Product Designer',
            'bio': 'Updated professional bio for 2026',
            'business_name': 'Design Co',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.full_name, 'Alicia T.')
        self.assertEqual(self.profile_a.title, 'Senior Product Designer')
        self.assertEqual(self.profile_a.bio, 'Updated professional bio for 2026')

    def test_idor_protection_user_b_cannot_view_user_a_order(self):
        """User B cannot view User A's order details."""
        package = ProductPackage.objects.create(
            name='Standard Matte',
            code='std-matte',
            price_ngn=25000
        )
        order_a = Order.objects.create(
            order_number='UZY-TEST-PRIV-01',
            user=self.user_a,
            package=package,
            amount=25000
        )
        order_url = reverse('dashboard:order_detail', kwargs={'order_number': order_a.order_number})
        
        # User A can view own order
        resp_a = self.client_a.get(order_url)
        self.assertEqual(resp_a.status_code, 200)

        # User B cannot view User A's order (should 404)
        resp_b = self.client_b.get(order_url)
        self.assertEqual(resp_b.status_code, 404)

    def test_account_deletion_unauthenticated_redirects(self):
        """Anonymous user cannot access delete account flow."""
        url = reverse('dashboard:delete_account')
        response = self.anon_client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_account_deletion_get_renders_confirmation_screen(self):
        """Authenticated user receives clear erasure warnings and options on GET."""
        url = reverse('dashboard:delete_account')
        response = self.client_a.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete Your Account')
        self.assertContains(response, 'permanent and non-reversible')
        self.assertContains(response, 'confirm_acknowledgment')
        self.assertContains(response, 'confirm_password')

    def test_account_deletion_post_without_acknowledgment_fails(self):
        """Account deletion fails if the acknowledgment checkbox is not checked."""
        url = reverse('dashboard:delete_account')
        response = self.client_a.post(url, {
            'confirm_password': self.password,
            # no confirm_acknowledgment
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please check the box confirming you understand')
        self.assertTrue(User.objects.filter(pk=self.user_a.pk).exists())

    def test_account_deletion_post_with_wrong_password_fails(self):
        """Account deletion fails if the confirmation password is incorrect."""
        url = reverse('dashboard:delete_account')
        response = self.client_a.post(url, {
            'confirm_acknowledgment': 'on',
            'confirm_password': 'WrongPassword999!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect password')
        self.assertTrue(User.objects.filter(pk=self.user_a.pk).exists())

    def test_account_deletion_success_flow(self):
        """
        Verified account deletion:
        - Decouples physical cards and resets to STATUS_UNASSIGNED
        - Cascades user profile & links
        - Terminates session
        - Purges User from database
        """
        card = Card.objects.create(
            card_code='TEST-CARD-PRIV-01',
            user=self.user_a,
            profile=self.profile_a,
            status=Card.STATUS_ACTIVE
        )
        CustomLink.objects.create(
            profile=self.profile_a,
            title='My Portfolio',
            url='https://portfolio.example.com'
        )

        user_a_id = self.user_a.pk
        profile_a_id = self.profile_a.pk
        card_id = card.pk

        url = reverse('dashboard:delete_account')
        response = self.client_a.post(url, {
            'confirm_acknowledgment': 'on',
            'confirm_password': self.password,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('core:home'))

        # User is deleted
        self.assertFalse(User.objects.filter(pk=user_a_id).exists())

        # Profile is deleted via cascade
        self.assertFalse(Profile.objects.filter(pk=profile_a_id).exists())

        # Card is sanitized: unlinked and status set to UNASSIGNED
        card.refresh_from_db()
        self.assertIsNone(card.user)
        self.assertIsNone(card.profile)
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)

    def test_admin_inquiry_category_filter(self):
        """Admin InquiryCategoryFilter isolates privacy requests properly."""
        msg_privacy = ContactMessage.objects.create(
            full_name='Data Subject',
            email='subject@example.com',
            subject='[Data Privacy Request] NDPA Subject Access Request',
            message='I want a copy of all my data.'
        )
        msg_general = ContactMessage.objects.create(
            full_name='General Inquirer',
            email='general@example.com',
            subject='Question about card delivery times',
            message='When can I expect my card?'
        )

        factory = RequestFactory()
        req_privacy = factory.get('/admin/core/contactmessage/?category=privacy')
        
        filt = InquiryCategoryFilter(req_privacy, {'category': ['privacy']}, ContactMessage, ContactMessageAdmin)
        qs = filt.queryset(req_privacy, ContactMessage.objects.all())
        
        self.assertIn(msg_privacy, qs)
        self.assertNotIn(msg_general, qs)

        req_general = factory.get('/admin/core/contactmessage/?category=general')
        filt_gen = InquiryCategoryFilter(req_general, {'category': ['general']}, ContactMessage, ContactMessageAdmin)
        qs_gen = filt_gen.queryset(req_general, ContactMessage.objects.all())
        
        self.assertIn(msg_general, qs_gen)
        self.assertNotIn(msg_privacy, qs_gen)
