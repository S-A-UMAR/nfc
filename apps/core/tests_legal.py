from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.core.models import ContactMessage
from apps.accounts.forms import UserRegisterForm
from apps.orders.models import ProductPackage

User = get_user_model()


class LegalSuiteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.legal_urls = [
            ('legal:index', 'Legal & Compliance Suite'),
            ('legal:privacy', 'Privacy Policy'),
            ('legal:terms', 'Terms of Service'),
            ('legal:cookies', 'Cookie Policy'),
            ('legal:acceptable_use', 'Acceptable Use Policy'),
            ('legal:refunds', 'Refund & Cancellation Policy'),
            ('legal:shipping', 'Shipping & Delivery Policy'),
            ('legal:nfc_terms', 'NFC Card Terms & Architecture'),
            ('legal:copyright', 'IP & Copyright Policy'),
            ('legal:user_content', 'User-Generated Content Policy'),
            ('legal:third_party', 'Third-Party Services Disclosure'),
            ('legal:complaints', 'Complaints &amp; Inquiries'),
        ]

    def test_all_eleven_legal_pages_load_successfully(self):
        """Verify each of the 11 legal documents + hub index returns HTTP 200 with correct title."""
        for url_name, expected_title in self.legal_urls:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected_title)
                # Verify standard legal sidebar is present
                self.assertContains(response, 'Compliance Suite')

    def test_privacy_policy_contains_ndpa_and_actual_flows(self):
        """Verify Privacy Policy includes NDPA 2023, data categories, and third-party disclosures."""
        response = self.client.get(reverse('legal:privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nigeria Data Protection Act 2023')
        self.assertContains(response, 'NDPA')
        self.assertContains(response, 'Paystack')
        self.assertContains(response, 'Brevo')
        self.assertContains(response, 'TiDB Cloud')
        self.assertContains(response, 'Cloudinary')

    def test_terms_of_service_contains_card_and_nigerian_jurisdiction(self):
        """Verify Terms of Service includes Nigerian governing law and hardware disclaimers."""
        response = self.client.get(reverse('legal:terms'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Federal Republic of Nigeria')
        self.assertContains(response, 'NFC Smart Cards')
        self.assertContains(response, 'Paystack')

    def test_cookie_policy_documents_essential_cookies(self):
        """Verify Cookie Policy accurately documents sessionid, csrftoken, and messages."""
        response = self.client.get(reverse('legal:cookies'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sessionid')
        self.assertContains(response, 'csrftoken')
        self.assertContains(response, 'Strictly Essential')
        self.assertContains(response, 'No Advertising Cookies')

    def test_acceptable_use_covers_fraud_and_phishing(self):
        """Verify Acceptable Use Policy covers Nigerian anti-fraud, impersonation, and AUP rules."""
        response = self.client.get(reverse('legal:acceptable_use'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Advance-Fee')
        self.assertContains(response, 'Impersonation')
        self.assertContains(response, 'Phishing')

    def test_refund_policy_details_hardware_warranty(self):
        """Verify Refund Policy covers hardware warranty and Paystack reversal terms."""
        response = self.client.get(reverse('legal:refunds'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Defective Hardware')
        self.assertContains(response, 'replacement card')
        self.assertContains(response, 'Paystack')

    def test_shipping_policy_details_nigerian_coverage(self):
        """Verify Shipping Policy covers all 36 states and delivery timelines."""
        response = self.client.get(reverse('legal:shipping'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nationwide Nigeria Delivery')
        self.assertContains(response, 'Lagos State')
        self.assertContains(response, 'Abuja')

    def test_nfc_terms_reflects_ntag216_architecture(self):
        """Verify NFC Card Terms accurately details NTAG216 chip and QR fallback."""
        response = self.client.get(reverse('legal:nfc_terms'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'NTAG216')
        self.assertContains(response, '13.56 MHz')
        self.assertContains(response, 'ISO/IEC 14443')
        self.assertContains(response, 'laser-printed QR')

    def test_copyright_policy_references_copyright_act_2022(self):
        """Verify Copyright Policy references the Nigerian Copyright Act 2022."""
        response = self.client.get(reverse('legal:copyright'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Copyright Act 2022')
        self.assertContains(response, 'Infringement Notice')

    def test_user_content_policy_covers_profile_uploads(self):
        """Verify UGC policy covers profile images, trade names, and moderation rights."""
        response = self.client.get(reverse('legal:user_content'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'User-Generated Content')
        self.assertContains(response, 'Profile and avatar photographs')

    def test_third_party_disclosure_lists_verified_providers(self):
        """Verify Third-Party Disclosure lists all 5 actual infrastructure providers."""
        response = self.client.get(reverse('legal:third_party'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paystack Payments Limited')
        self.assertContains(response, 'Brevo (Sendinblue SAS)')
        self.assertContains(response, 'TiDB Cloud (PingCAP, Inc.)')
        self.assertContains(response, 'Cloudinary Ltd')
        self.assertContains(response, 'Render Services, Inc.')

    def test_complaints_page_handles_get_with_category(self):
        """Verify Complaints page pre-fills subject when category query param is passed."""
        response = self.client.get(reverse('legal:complaints') + '?category=privacy')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '[Data Privacy Request]')

    def test_complaints_submission_creates_contact_message(self):
        """Verify submitting the complaints form creates a ContactMessage record."""
        initial_count = ContactMessage.objects.count()
        payload = {
            'full_name': 'Chidi Okafor',
            'email': 'chidi.okafor@example.com',
            'phone': '+2348033334444',
            'subject': '[Data Privacy Request] Deletion Request',
            'message': 'Please delete my profile data in accordance with NDPA 2023 section 34.'
        }
        response = self.client.post(reverse('legal:complaints'), payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), initial_count + 1)
        msg = ContactMessage.objects.latest('id')
        self.assertEqual(msg.full_name, 'Chidi Okafor')
        self.assertEqual(msg.subject, '[Data Privacy Request] Deletion Request')
        self.assertContains(response, 'Your inquiry / formal complaint has been received')

    def test_footer_contains_all_legal_links(self):
        """Verify the master footer in base.html renders working links to the legal suite."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('legal:privacy'))
        self.assertContains(response, reverse('legal:terms'))
        self.assertContains(response, reverse('legal:cookies'))
        self.assertContains(response, reverse('legal:acceptable_use'))
        self.assertContains(response, reverse('legal:refunds'))
        self.assertContains(response, reverse('legal:shipping'))
        self.assertContains(response, reverse('legal:nfc_terms'))
        self.assertContains(response, reverse('legal:copyright'))
        self.assertContains(response, reverse('legal:user_content'))
        self.assertContains(response, reverse('legal:third_party'))
        self.assertContains(response, reverse('legal:complaints'))

    def test_registration_terms_acceptance_validation(self):
        """Verify UserRegisterForm strictly requires agree_terms=True server-side."""
        # Unchecked agree_terms should fail
        form_data_unchecked = {
            'first_name': 'Ibrahim',
            'last_name': 'Musa',
            'email': 'ibrahim@example.com',
            'phone': '+2348011112222',
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
            'agree_terms': False,
        }
        form = UserRegisterForm(data=form_data_unchecked)
        self.assertFalse(form.is_valid())
        self.assertIn('agree_terms', form.errors)

        # Checked agree_terms should pass
        form_data_checked = {
            'first_name': 'Ibrahim',
            'last_name': 'Musa',
            'email': 'ibrahim.valid@example.com',
            'phone': '+2348011112222',
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
            'agree_terms': True,
        }
        form_valid = UserRegisterForm(data=form_data_checked)
        self.assertTrue(form_valid.is_valid())

    def test_registration_template_has_live_legal_links(self):
        """Verify register.html links to the real legal:terms and legal:privacy URLs."""
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('legal:terms'))
        self.assertContains(response, reverse('legal:privacy'))

    def test_checkout_template_has_legal_disclosures(self):
        """Verify checkout.html includes links to terms, nfc terms, shipping, and refunds."""
        user = User.objects.create_user(
            email='checkout.legal@example.com',
            password='TestPassword123!',
            first_name='Checkout',
            last_name='User'
        )
        self.client.force_login(user)

        pkg = ProductPackage.objects.first()
        if not pkg:
            pkg = ProductPackage.objects.create(
                code='legal-test-pkg',
                name='Legal Test Card',
                package_type='card_only',
                price_ngn=25000,
                description='Test card description',
                features='Feature 1\nFeature 2'
            )
        response = self.client.get(reverse('orders:checkout', kwargs={'package_code': pkg.code}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('legal:terms'))
        self.assertContains(response, reverse('legal:nfc_terms'))
        self.assertContains(response, reverse('legal:shipping'))
        self.assertContains(response, reverse('legal:refunds'))

    def test_sitemap_includes_legal_urls(self):
        """Verify /sitemap.xml contains legal URLs."""
        response = self.client.get(reverse('django.contrib.sitemaps.views.sitemap'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/legal/privacy/')
        self.assertContains(response, '/legal/terms/')
        self.assertContains(response, '/legal/cookies/')
