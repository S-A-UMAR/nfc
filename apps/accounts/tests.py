from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile

User = get_user_model()

class Phase2AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('accounts:register')
        self.login_url = reverse('accounts:login')
        self.logout_url = reverse('accounts:logout')
        self.dashboard_url = reverse('dashboard:overview')
        
        self.user_data = {
            'first_name': 'Sarah',
            'last_name': 'Connor',
            'email': 'sarah@example.com',
            'phone': '+2348011223344',
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
            'agree_terms': 'on',
        }

    def test_1_registration_creates_django_user_and_profile(self):
        """TEST 1: Register a new user and confirm user and profile exist in database."""
        response = self.client.post(self.register_url, self.user_data, follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify User created in DB
        user = User.objects.filter(email='sarah@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'Sarah')
        self.assertEqual(user.last_name, 'Connor')
        
        # Verify Password is properly hashed by Django
        self.assertTrue(user.check_password('SecurePassword123!'))
        self.assertNotEqual(user.password, 'SecurePassword123!')
        
        # Verify linked Profile auto-provisioned
        profile = Profile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)
        self.assertEqual(profile.full_name, 'Sarah Connor')

    def test_2_logout_terminates_session(self):
        """TEST 2: Register/login, then log out and confirm session termination."""
        self.client.post(self.register_url, self.user_data)
        self.assertTrue('_auth_user_id' in self.client.session)
        
        # Logout
        response = self.client.get(self.logout_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_3_login_with_valid_credentials(self):
        """TEST 3: Log in using saved credentials and verify session creation."""
        # Pre-create user
        User.objects.create_user(
            email='sarah@example.com',
            password='SecurePassword123!',
            first_name='Sarah',
            last_name='Connor'
        )
        
        login_data = {
            'username': 'sarah@example.com',
            'password': 'SecurePassword123!'
        }
        response = self.client.post(self.login_url, login_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('_auth_user_id' in self.client.session)
        self.assertRedirects(response, self.dashboard_url)

    def test_4_login_with_incorrect_password_fails(self):
        """TEST 4: Attempt to log in with an incorrect password and confirm failure."""
        User.objects.create_user(
            email='sarah@example.com',
            password='SecurePassword123!',
            first_name='Sarah',
            last_name='Connor'
        )
        
        login_data = {
            'username': 'sarah@example.com',
            'password': 'WRONG_PASSWORD'
        }
        response = self.client.post(self.login_url, login_data, follow=False)
        self.assertEqual(response.status_code, 200) # Form re-rendered with errors
        self.assertFalse('_auth_user_id' in self.client.session)
        self.assertContains(response, 'Invalid email or password')

    def test_5_dashboard_protection_redirects_unauthenticated(self):
        """TEST 5: Open the dashboard while logged out and confirm access is denied."""
        response = self.client.get(self.dashboard_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_6_session_persistence_on_refresh(self):
        """TEST 6: Confirm refreshing or navigating while logged in preserves session."""
        self.client.post(self.register_url, self.user_data)
        user_id = self.client.session.get('_auth_user_id')
        self.assertIsNotNone(user_id)
        
        # Access dashboard multiple times (simulating page refresh / navigation)
        resp1 = self.client.get(self.dashboard_url)
        self.assertEqual(resp1.status_code, 200)
        
        resp2 = self.client.get(self.dashboard_url)
        self.assertEqual(resp2.status_code, 200)
        
        # Confirm user is still authenticated
        self.assertEqual(self.client.session.get('_auth_user_id'), user_id)
