from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth import get_user_model
from apps.cards.models import Card
from apps.accounts.models import OTPCode
from apps.profiles.models import Profile

User = get_user_model()


class NFCAuthContinuityTests(TestCase):
    """
    Focused test suite for Batch 1: NFC Activation Authentication Continuity.
    Verifies that customers who tap an unactivated STRIDE card can sign in or register,
    complete OTP verification, and return seamlessly to the card's activation URL.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.card_code = 'ST-TEST-001'
        self.card = Card.objects.create(
            card_code=self.card_code,
            status=Card.STATUS_RESERVED
        )
        self.activation_pin = self.card.generate_activation_code()
        self.card.save()

        # Existing user
        self.existing_password = 'ComplexPassword123!'
        self.existing_user = User.objects.create_user(
            email='existing.customer@example.com',
            password=self.existing_password,
            first_name='Existing',
            last_name='Customer',
            is_email_verified=True
        )
        Profile.objects.get_or_create(user=self.existing_user)

    def test_1_existing_customer_login_from_nfc_activation(self):
        """1. Existing customer logs in with ?next=/c/<card_code>/ and redirects back to card."""
        target_url = f"/c/{self.card_code}/"
        login_url = f"{reverse('accounts:login')}?next={target_url}"

        # GET login page with next param
        resp = self.client.get(login_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="next" value="{target_url}"')

        # POST login with valid credentials
        resp_post = self.client.post(reverse('accounts:login'), {
            'username': self.existing_user.email,
            'password': self.existing_password,
            'next': target_url
        })
        self.assertRedirects(resp_post, target_url, fetch_redirect_response=False)

    def test_2_new_customer_registration_and_otp_verification(self):
        """2. New customer registers with ?next=/c/<card_code>/, verifies OTP, and redirects back to card."""
        target_url = f"/c/{self.card_code}/"
        reg_url = f"{reverse('accounts:register')}?next={target_url}"

        # GET register page with next param
        resp = self.client.get(reg_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="next" value="{target_url}"')

        # POST registration
        new_email = 'new.customer@example.com'
        reg_data = {
            'first_name': 'New',
            'last_name': 'Customer',
            'email': new_email,
            'password': 'SecurePassword2026!',
            'password_confirm': 'SecurePassword2026!',
            'agree_terms': 'on',
            'next': target_url
        }
        resp_post = self.client.post(reverse('accounts:register'), reg_data)
        self.assertRedirects(resp_post, reverse('accounts:verify_otp'))

        # Session should preserve auth_next
        self.assertEqual(self.client.session.get('auth_next'), target_url)

        # Generate a known valid OTP for the registered user
        user = User.objects.get(email=new_email)
        _, plain_otp = OTPCode.generate_otp(
            user=user,
            email=new_email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )

        # Verify OTP
        otp_resp = self.client.post(reverse('accounts:verify_otp'), {
            'otp_code': plain_otp
        })
        self.assertRedirects(otp_resp, target_url, fetch_redirect_response=False)

    def test_3_registration_form_validation_failure_preserves_next(self):
        """3. Registration validation error retains ?next= and redirects back to card after correction."""
        target_url = f"/c/{self.card_code}/"
        new_email = 'retry.register@example.com'

        # First attempt: Passwords do not match
        bad_data = {
            'first_name': 'Retry',
            'last_name': 'User',
            'email': new_email,
            'password': 'FirstPassword123!',
            'password_confirm': 'MismatchedPassword123!',
            'agree_terms': 'on',
            'next': target_url
        }
        resp_fail = self.client.post(reverse('accounts:register'), bad_data)
        self.assertEqual(resp_fail.status_code, 200)
        self.assertContains(resp_fail, 'Passwords do not match')
        # next field preserved in re-rendered form
        self.assertContains(resp_fail, f'name="next" value="{target_url}"')

        # Second attempt: Correct passwords
        good_data = {
            'first_name': 'Retry',
            'last_name': 'User',
            'email': new_email,
            'password': 'CorrectPassword123!',
            'password_confirm': 'CorrectPassword123!',
            'agree_terms': 'on',
            'next': target_url
        }
        resp_good = self.client.post(reverse('accounts:register'), good_data)
        self.assertRedirects(resp_good, reverse('accounts:verify_otp'))

        # OTP Verification
        user = User.objects.get(email=new_email)
        _, plain_otp = OTPCode.generate_otp(
            user=user,
            email=new_email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        otp_resp = self.client.post(reverse('accounts:verify_otp'), {
            'otp_code': plain_otp
        })
        self.assertRedirects(otp_resp, target_url, fetch_redirect_response=False)

    def test_4_incorrect_login_credentials_preserves_next(self):
        """4. Failed login attempt preserves return destination for subsequent successful login."""
        target_url = f"/c/{self.card_code}/"
        login_url = f"{reverse('accounts:login')}?next={target_url}"

        # GET login
        self.client.get(login_url)

        # 1st attempt: wrong password
        resp_fail = self.client.post(reverse('accounts:login'), {
            'username': self.existing_user.email,
            'password': 'WrongPassword999!',
            'next': target_url
        })
        self.assertEqual(resp_fail.status_code, 200)
        self.assertContains(resp_fail, "Invalid email or password")
        self.assertContains(resp_fail, f'name="next" value="{target_url}"')

        # 2nd attempt: correct password
        resp_success = self.client.post(reverse('accounts:login'), {
            'username': self.existing_user.email,
            'password': self.existing_password,
            'next': target_url
        })
        self.assertRedirects(resp_success, target_url, fetch_redirect_response=False)

    def test_5_expired_or_incorrect_otp_preserves_destination(self):
        """5. Incorrect OTP attempts do not discard auth_next; valid attempt succeeds to card."""
        target_url = f"/c/{self.card_code}/"
        new_email = 'otp.retry@example.com'

        # Register
        self.client.post(reverse('accounts:register'), {
            'first_name': 'OTP',
            'last_name': 'Retry',
            'email': new_email,
            'password': 'ValidPassword123!',
            'password_confirm': 'ValidPassword123!',
            'agree_terms': 'on',
            'next': target_url
        })

        # Submit wrong OTP
        wrong_resp = self.client.post(reverse('accounts:verify_otp'), {
            'otp_code': '000000'
        })
        self.assertEqual(wrong_resp.status_code, 200)
        # auth_next must still be in session
        self.assertEqual(self.client.session.get('auth_next'), target_url)

        # Submit valid OTP
        user = User.objects.get(email=new_email)
        _, plain_otp = OTPCode.generate_otp(
            user=user,
            email=new_email,
            purpose=OTPCode.PURPOSE_EMAIL_VERIFICATION
        )
        valid_resp = self.client.post(reverse('accounts:verify_otp'), {
            'otp_code': plain_otp
        })
        self.assertRedirects(valid_resp, target_url, fetch_redirect_response=False)

    def test_6_normal_login_without_next(self):
        """6. Normal login without next redirects to dashboard overview."""
        resp = self.client.post(reverse('accounts:login'), {
            'username': self.existing_user.email,
            'password': self.existing_password
        })
        self.assertRedirects(resp, reverse('dashboard:overview'))

    def test_7_malicious_external_redirect_rejected(self):
        """7. Malicious external URLs in next are rejected and fallback to dashboard."""
        malicious_urls = [
            'http://attacker.com/evil',
            'https://evil.com/phish',
            'http://testserver.evil.com/'
        ]
        for bad_url in malicious_urls:
            cache.clear()
            # Login attempt with external next
            resp = self.client.post(reverse('accounts:login'), {
                'username': self.existing_user.email,
                'password': self.existing_password,
                'next': bad_url
            })
            # Must redirect safely to dashboard overview, NOT the malicious domain
            self.assertRedirects(resp, reverse('dashboard:overview'))
            self.client.logout()

    def test_8_protocol_relative_redirect_rejected(self):
        """8. Protocol-relative and backslash evasion attempts are rejected."""
        proto_relative_urls = [
            '//attacker.com/evil',
            '/\\attacker.com/evil',
            '\\\\attacker.com\\evil'
        ]
        for bad_url in proto_relative_urls:
            cache.clear()
            resp = self.client.post(reverse('accounts:login'), {
                'username': self.existing_user.email,
                'password': self.existing_password,
                'next': bad_url
            })
            self.assertRedirects(resp, reverse('dashboard:overview'))
            self.client.logout()

    def test_9_unauthenticated_activation_attempt(self):
        """9. Unauthenticated users visiting /c/<card_code>/ see activation welcome; direct POST is blocked."""
        # Unauthenticated GET /c/<card_code>/ renders card_unassigned.html
        resp_get = self.client.get(f"/c/{self.card_code}/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, f"{reverse('accounts:login')}?next=/c/{self.card_code}/")
        self.assertContains(resp_get, f"{reverse('accounts:register')}?next=/c/{self.card_code}/")

        # Unauthenticated direct POST to /activate/ redirects to login
        resp_post = self.client.post(reverse('cards:card_activate'), {
            'card_code': self.card_code,
            'activation_code': self.activation_pin
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(resp_post.url.startswith(reverse('accounts:login')))

    def test_10_correct_card_id_preserved_after_authentication(self):
        """10. After login, returning to /c/<card_code>/ shows card ID prefilled and card is not activated automatically."""
        target_url = f"/c/{self.card_code}/"

        # Sign in with return target
        resp_login = self.client.post(reverse('accounts:login'), {
            'username': self.existing_user.email,
            'password': self.existing_password,
            'next': target_url
        })
        self.assertRedirects(resp_login, target_url, fetch_redirect_response=False)

        # Follow redirect to card destination as authenticated user
        resp_card = self.client.get(target_url)
        self.assertEqual(resp_card.status_code, 200)
        # Card ID is prefilled in form
        self.assertContains(resp_card, f'value="{self.card_code}"')
        # User is recognized as authenticated
        self.assertContains(resp_card, self.existing_user.email)
        # Activation PIN field is presented
        self.assertContains(resp_card, 'name="activation_code"')
        # Card is NOT activated automatically (status remains RESERVED)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_RESERVED)
        self.assertIsNone(self.card.activated_at)
