from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.core.models import ContactMessage
from apps.profiles.models import Profile

User = get_user_model()


class Phase4IPAssetsAndThirdPartyTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Regular user A
        self.user = User.objects.create_user(
            email='phase4.user@example.com',
            password='Password123!',
            first_name='Phase4',
            last_name='User'
        )
        self.profile = self.user.profile
        self.profile.full_name = 'Phase 4 User'
        self.profile.slug = 'phase4-user'
        self.profile.bio = 'Creative professional testing UZYRA Phase 4 asset protection.'
        self.profile.save()

        # Staff user
        self.staff_user = User.objects.create_user(
            email='ops.staff@example.com',
            password='Password123!',
            first_name='Ops',
            last_name='Staff',
            is_staff=True
        )

    def test_third_party_disclosure_includes_google_fonts_and_all_providers(self):
        """Verify Third-Party Services Disclosure lists all 6 infrastructure providers including Google Fonts."""
        response = self.client.get(reverse('legal:third_party'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paystack Payments Limited')
        self.assertContains(response, 'Brevo (Sendinblue SAS)')
        self.assertContains(response, 'TiDB Cloud (PingCAP, Inc.)')
        self.assertContains(response, 'Cloudinary Ltd')
        self.assertContains(response, 'Render Services, Inc.')
        self.assertContains(response, 'Google Fonts (Google LLC)')

    def test_copyright_infringement_complaint_submission(self):
        """Verify submitting a copyright infringement report creates a ContactMessage record."""
        url = reverse('legal:complaints') + '?category=copyright'
        resp_get = self.client.get(url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, '[IP / Copyright Notice]')

        # Submit copyright notice
        payload = {
            'full_name': 'Original Creator',
            'email': 'creator@example.com',
            'phone': '+2348099998888',
            'subject': '[IP / Copyright Notice] Unauthorized Photo Use',
            'message': 'Infringing photo published at /u/phase4-user/. Proof of registration attached.'
        }
        resp_post = self.client.post(reverse('legal:complaints'), payload, follow=True)
        self.assertEqual(resp_post.status_code, 200)

        msg = ContactMessage.objects.filter(email='creator@example.com').first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.full_name, 'Original Creator')
        self.assertEqual(msg.subject, '[IP / Copyright Notice] Unauthorized Photo Use')
        self.assertIn('[IP / Copyright Notice]', msg.subject)

    def test_unauthorized_user_cannot_access_operations_inquiry_detail(self):
        """Verify regular users cannot access operations portal inquiry triage detail."""
        from apps.core.models import BusinessInquiry
        inquiry = BusinessInquiry.objects.create(
            full_name='Complainant',
            email='complainant@example.com',
            message='Test infringement report'
        )

        # Anonymous user -> redirected to ops login (302)
        url_ops = reverse('operations:inquiry_detail', args=[inquiry.id])
        resp_anon = self.client.get(url_ops)
        self.assertEqual(resp_anon.status_code, 302)

        # Regular authenticated non-staff user -> forbidden (403) or redirected (302)
        self.client.force_login(self.user)
        resp_user = self.client.get(url_ops)
        self.assertIn(resp_user.status_code, [302, 403])

        # Staff user -> granted access
        self.client.force_login(self.staff_user)
        resp_staff = self.client.get(url_ops)
        self.assertEqual(resp_staff.status_code, 200)
        self.assertContains(resp_staff, 'Complainant')

    def test_public_profile_user_content_isolation(self):
        """Verify public profile renders user content while isolating internal database & auth details."""
        url_profile = reverse('profiles:public_profile', args=[self.profile.slug])
        response = self.client.get(url_profile)
        self.assertEqual(response.status_code, 200)

        # Rendered public user content
        self.assertContains(response, 'Phase 4 User')
        self.assertContains(response, 'Creative professional testing UZYRA Phase 4 asset protection.')

        # Secret / internal fields must NOT be exposed
        self.assertNotContains(response, self.user.password)
        self.assertNotContains(response, 'is_staff')
        self.assertNotContains(response, 'is_superuser')

    def test_legal_pages_contain_no_overpromising_claims(self):
        """Verify legal pages use factual wording and refrain from overpromising legal claims."""
        pages = ['legal:privacy', 'legal:terms', 'legal:copyright', 'legal:user_content']
        for p in pages:
            with self.subTest(page=p):
                resp = self.client.get(reverse(p))
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, '100% secure')
                self.assertNotContains(resp, 'completely anonymous')
                self.assertNotContains(resp, 'copyright-free')
                self.assertNotContains(resp, 'GDPR certified')
