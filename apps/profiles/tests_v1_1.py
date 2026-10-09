from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.profiles.models import Profile, ContactExchange
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

class GrowthFeaturesV11Tests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='usera@example.com',
            password='Password123!',
            first_name='User',
            last_name='A'
        )
        self.profile_a = self.user_a.profile
        self.profile_a.full_name = "User A"
        self.profile_a.save()

        self.user_b = User.objects.create_user(
            email='userb@example.com',
            password='Password123!',
            first_name='User',
            last_name='B'
        )
        self.profile_b = self.user_b.profile

    def test_contact_exchange_valid_submission(self):
        """Test a visitor submitting valid contact details to User A's profile."""
        url = reverse('profiles:submit_contact_exchange', kwargs={'slug': self.profile_a.slug})
        payload = {
            'full_name': 'John Visitor',
            'email': 'john@visitor.com',
            'phone': '+2348011112222',
            'business_name': 'Visitor Corp',
            'notes': 'Interested in partnership',
            'consent_given': 'on'
        }
        response = self.client.post(url, payload)
        self.assertIn(response.status_code, [200, 302])

        # Verify DB record created cleanly
        lead = ContactExchange.objects.filter(profile=self.profile_a, full_name='John Visitor').first()
        self.assertIsNotNone(lead)
        self.assertEqual(lead.email, 'john@visitor.com')
        self.assertTrue(lead.consent_given)

    def test_contact_exchange_requires_email_or_phone(self):
        """Test contact exchange fails if neither email nor phone is provided."""
        url = reverse('profiles:submit_contact_exchange', kwargs={'slug': self.profile_a.slug})
        payload = {
            'full_name': 'Empty Visitor',
            'consent_given': 'on'
        }
        response = self.client.post(url, payload)
        self.assertEqual(ContactExchange.objects.filter(full_name='Empty Visitor').count(), 0)

    def test_contact_exchange_requires_consent(self):
        """Test contact exchange fails if consent is missing."""
        url = reverse('profiles:submit_contact_exchange', kwargs={'slug': self.profile_a.slug})
        payload = {
            'full_name': 'No Consent Visitor',
            'email': 'noconsent@example.com',
        }
        response = self.client.post(url, payload)
        self.assertEqual(ContactExchange.objects.filter(full_name='No Consent Visitor').count(), 0)

    def test_contact_exchange_dashboard_idor_isolation(self):
        """Test User B cannot view or delete User A's received contacts."""
        lead = ContactExchange.objects.create(
            profile=self.profile_a,
            full_name='Secret Lead',
            email='secret@example.com',
            consent_given=True
        )

        # Log in as User B
        self.client.login(email='userb@example.com', password='Password123!')
        
        # Dashboard contacts should not list Lead belonging to User A
        response = self.client.get(reverse('dashboard:contacts_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Secret Lead', response.content.decode('utf-8'))

        # Attempt to delete User A's lead as User B
        delete_url = reverse('dashboard:contact_delete', kwargs={'contact_id': lead.id})
        del_resp = self.client.post(delete_url)
        self.assertEqual(del_resp.status_code, 404)
        self.assertTrue(ContactExchange.objects.filter(id=lead.id).exists())

    def test_free_profile_qr_code_generation(self):
        """Test public profile QR code endpoint generates valid PNG image."""
        qr_url = reverse('profiles:download_profile_qr', kwargs={'slug': self.profile_a.slug})
        response = self.client.get(qr_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
