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
