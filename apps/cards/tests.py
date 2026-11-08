from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile
from apps.cards.models import Card, CardEvent
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

class Phase6SmartCardTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Create User & Profile
        self.user = User.objects.create_user(
            email='cardowner@example.com',
            password='Password123!',
            first_name='Card',
            last_name='Owner'
        )
        self.profile = self.user.profile
        self.profile.full_name = 'Card Owner'
        self.profile.slug = 'card-owner'
        self.profile.save()
        
        # Create Card
        self.card = Card.objects.create(
            card_code='BR-000001',
            user=self.user,
            profile=self.profile,
            status=Card.STATUS_ACTIVE
        )

    def test_1_active_card_redirects_to_public_profile(self):
        """TEST 1: ACTIVE card redirects to assigned public profile and logs events."""
        url = f'/c/{self.card.card_code}/'
        response = self.client.get(url, follow=False)
        
        # Verify HTTP 302 Redirect to /u/card-owner/
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/u/{self.profile.slug}/', response.url)
        
        # Verify CardEvent and AnalyticsEvent logged
        self.assertTrue(CardEvent.objects.filter(card=self.card).exists())
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile, card=self.card).exists())

    def test_active_card_with_direct_link_mode_redirects_to_direct_url(self):
        """Active card with direct link mode routes visitor directly to target URL and logs analytics."""
        self.profile.direct_link_enabled = True
        self.profile.direct_link_url = 'https://calendly.com/cardowner/30min'
        self.profile.save()

        url = f'/c/{self.card.card_code}/'
        response = self.client.get(url, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://calendly.com/cardowner/30min')

        # Verify analytics and tap event still properly tracked
        self.assertTrue(CardEvent.objects.filter(card=self.card).exists())
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile, card=self.card).exists())


    def test_2_lost_card_renders_security_notice(self):
        """TEST 2: Change status to LOST — profile does NOT open, lost notice rendered."""
        self.card.status = Card.STATUS_LOST
        self.card.save()
        
        url = f'/c/{self.card.card_code}/'
        response = self.client.get(url, follow=False)
        
        self.assertEqual(response.status_code, 200) # Does NOT redirect
        self.assertContains(response, 'This card has been reported lost')
        self.assertContains(response, 'Card Inactive')

    def test_3_suspended_card_renders_inactive_notice(self):
        """TEST 3: Change status to SUSPENDED — profile does NOT open, suspended notice rendered."""
        self.card.status = Card.STATUS_SUSPENDED
        self.card.save()
        
        url = f'/c/{self.card.card_code}/'
        response = self.client.get(url, follow=False)
        
        self.assertEqual(response.status_code, 200) # Does NOT redirect
        self.assertContains(response, 'This card is currently inactive')
        self.assertContains(response, 'Card Suspended')

    def test_4_invalid_card_code_renders_branded_404(self):
        """TEST 4: Invalid card code renders branded 404 page with status code 404."""
        invalid_url = '/c/INVALID-CARD-999/'
        response = self.client.get(invalid_url, follow=False)
        
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Card Not Found', status_code=404)

    def test_5_unassigned_card_renders_activation_notice(self):
        """Unassigned card renders activation notice page."""
        self.card.status = Card.STATUS_UNASSIGNED
        self.card.save()
        
        url = f'/c/{self.card.card_code}/'
        response = self.client.get(url, follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activate Smart Card')


class Phase7CardAdminWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='admincustomer@example.com',
            password='Password123!',
            first_name='Admin',
            last_name='Customer'
        )
        self.profile = self.user.profile
        self.profile.slug = 'admin-customer'
        self.profile.save()

    def test_complete_card_admin_lifecycle_workflow(self):
        """
        Phase 7 Workflow Test:
        1. Create a new card (defaults to UNASSIGNED).
        2. Confirm status is UNASSIGNED.
        3. Assign card to a profile.
        4. Change status to ACTIVE.
        5. Visit card URL & confirm HTTP 302 redirect.
        6. Change status to LOST.
        7. Confirm it stops redirecting and shows lost security notice.
        """
        # Step 1: Create new card without setting status explicitly
        card = Card.objects.create(card_code='BR-777001')
        
        # Step 2: Confirm status is UNASSIGNED
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNone(card.user)
        self.assertIsNone(card.profile)
        
        # Unassigned card URL does NOT redirect to profile
        resp_unassigned = self.client.get(f'/c/{card.card_code}/')
        self.assertEqual(resp_unassigned.status_code, 200)
        self.assertContains(resp_unassigned, 'Activate Smart Card')
        
        # Step 3: Assign card to user & profile
        card.user = self.user
        card.profile = self.profile
        
        # Step 4: Change status to ACTIVE
        card.status = Card.STATUS_ACTIVE
        card.save()
        
        # Step 5 & 6: Visit card URL & confirm HTTP 302 redirect to profile
        resp_active = self.client.get(f'/c/{card.card_code}/', follow=False)
        self.assertEqual(resp_active.status_code, 302)
        self.assertIn(f'/u/{self.profile.slug}/', resp_active.url)
        
        # Step 7: Change status to LOST
        card.status = Card.STATUS_LOST
        card.save()
        
        # Step 8: Confirm it stops redirecting and shows security notice
        resp_lost = self.client.get(f'/c/{card.card_code}/', follow=False)
        self.assertEqual(resp_lost.status_code, 200)
        self.assertContains(resp_lost, 'This card has been reported lost')


class Phase3BCardSecurityTests(TestCase):
    """
    Security regression test suite for Phase 3B:
    1. check_activation_code rejection on missing hash, empty PIN, wrong PIN.
    2. check_activation_code constant-time matching on valid PIN.
    3. card_activate_view rejection when card lacks activation_code_hash.
    4. card_activate_view rejection on wrong PIN.
    5. card_activate_view success on valid PIN.
    6. Preservation of legitimate active cards and prohibition of re-activation.
    7. No leakage of secret PIN in messages or responses.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='security_user@example.com',
            password='Password123!',
            first_name='Sec',
            last_name='User'
        )
        self.profile = self.user.profile
        self.profile.slug = 'sec-user'
        self.profile.save()

    def test_check_activation_code_missing_hash_rejected(self):
        """Cards with no activation_code_hash must NEVER validate as true."""
        card = Card.objects.create(card_code='SEC-NOHASH-01', status=Card.STATUS_UNASSIGNED)
        self.assertIsNone(card.activation_code_hash)
        self.assertFalse(card.check_activation_code(''))
        self.assertFalse(card.check_activation_code('TEST-1234'))
        self.assertFalse(card.check_activation_code('ANYTHING'))
        self.assertFalse(card.check_activation_code(None))

    def test_check_activation_code_empty_code_rejected(self):
        """Empty or whitespace PINs must fail verification."""
        card = Card.objects.create(card_code='SEC-EMPTY-01', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code('VALID-PIN-12')
        card.save()

        self.assertFalse(card.check_activation_code(''))
        self.assertFalse(card.check_activation_code('   '))
        self.assertFalse(card.check_activation_code(None))

    def test_check_activation_code_wrong_code_rejected(self):
        """Mismatched PINs must fail constant-time verification."""
        card = Card.objects.create(card_code='SEC-WRONG-01', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code('SECRET-PIN-99')
        card.save()

        self.assertFalse(card.check_activation_code('SECRET-PIN-00'))
        self.assertFalse(card.check_activation_code('WRONG-PIN'))

    def test_check_activation_code_valid_code_accepted(self):
        """Matching PINs must pass constant-time verification with case and whitespace trimming."""
        card = Card.objects.create(card_code='SEC-VALID-01', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code('ABCD-1234')
        card.save()

        self.assertTrue(card.check_activation_code('ABCD-1234'))
        self.assertTrue(card.check_activation_code('abcd-1234'))
        self.assertTrue(card.check_activation_code('  AbCd-1234  '))

    def test_card_activate_view_missing_hash_requires_support(self):
        """Unassigned cards with no activation hash cannot be activated online and instruct to contact support."""
        card = Card.objects.create(card_code='SEC-LEGACY-01', status=Card.STATUS_UNASSIGNED)
        self.client.force_login(self.user)

        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'SEC-LEGACY-01',
            'activation_code': 'ANY-PIN',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "does not have an activation PIN configured. Please contact STRIDE support")
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNone(card.user)

    def test_card_activate_view_invalid_pin_rejected(self):
        """Invalid PIN rejects activation and preserves unassigned state."""
        card = Card.objects.create(card_code='SEC-CARD-02', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code('CORRECT-PIN')
        card.save()

        self.client.force_login(self.user)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'SEC-CARD-02',
            'activation_code': 'WRONG-PIN-XYZ',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid activation code")
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNone(card.user)

    def test_card_activate_view_valid_pin_succeeds(self):
        """Valid PIN successfully binds card to user and marks it active."""
        card = Card.objects.create(card_code='SEC-CARD-03', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code('CORRECT-PIN')
        card.save()

        self.client.force_login(self.user)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'SEC-CARD-03',
            'activation_code': 'CORRECT-PIN',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "is now activated")
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertEqual(card.user, self.user)
        self.assertEqual(card.profile, self.profile)
        self.assertIsNotNone(card.activated_at)

    def test_card_activate_view_already_active_rejected(self):
        """Already active card cannot be re-activated by customer."""
        other_user = User.objects.create_user(
            email='other_owner@example.com',
            password='Password123!',
            first_name='Other',
            last_name='User'
        )
        card = Card.objects.create(
            card_code='SEC-ACTIVE-01',
            user=other_user,
            profile=other_user.profile,
            status=Card.STATUS_ACTIVE
        )
        card.set_activation_code('PIN-1234')
        card.save()

        self.client.force_login(self.user)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'SEC-ACTIVE-01',
            'activation_code': 'PIN-1234',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already active and in use")
        card.refresh_from_db()
        self.assertEqual(card.user, other_user)

    def test_card_activate_view_pin_not_leaked_in_response(self):
        """Neither submitted PIN nor PIN hash appears anywhere in response messages or HTML."""
        secret_pin = "SUPER-SECRET-PIN-999"
        card = Card.objects.create(card_code='SEC-LEAK-01', status=Card.STATUS_UNASSIGNED)
        card.set_activation_code(secret_pin)
        card.save()

        self.client.force_login(self.user)
        resp = self.client.post(reverse('cards:card_activate'), {
            'card_code': 'SEC-LEAK-01',
            'activation_code': 'WRONG-PIN',
        }, follow=True)

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, secret_pin)
        self.assertNotContains(resp, card.activation_code_hash)

