import logging
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.core.services.email_service import BrevoEmailService
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.cards.models import Card

User = get_user_model()


class BrevoStagingEmailAllowlistTests(TestCase):
    """
    Focused verification for the Brevo Staging Email Recipient Allowlist.
    Validates fail-closed behavior, case normalization, wildcard domains,
    CC/BCC handling, production preservation, and caller resilience.
    """

    def setUp(self):
        self.client = Client()
        self.approved_email = "tester@strideid.com"
        self.unapproved_email = "external_customer@gmail.com"
        self.subject = "Test Transactional Email"
        self.html = "<p>Test Content</p>"

    def test_staging_with_approved_recipient(self):
        """Approved recipient in staging allowlist is permitted."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='tester@strideid.com,qa@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email=self.approved_email,
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res.get('success'))
            self.assertNotEqual(res.get('mode'), 'blocked_staging')

    def test_staging_with_unapproved_recipient(self):
        """Unapproved recipient in staging is blocked with safe log entry and blocked status."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='tester@strideid.com'
        ):
            with self.assertLogs('stride.email_service', level='WARNING') as cm:
                res = BrevoEmailService.send_transactional_email(
                    to_email=self.unapproved_email,
                    subject=self.subject,
                    html_content=self.html
                )
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')
            self.assertEqual(res.get('status'), 'blocked_staging')
            self.assertIn("STAGING_EMAIL_ALLOWLIST", res.get('error'))
            # Log must carry the identifier but must NOT expose the recipient address
            self.assertTrue(any("[STAGING EMAIL BLOCKED]" in log for log in cm.output))
            self.assertFalse(any(self.unapproved_email in log for log in cm.output))

    def test_staging_with_empty_allowlist_fails_closed(self):
        """Staging fails closed if STAGING_EMAIL_ALLOWLIST is configured as empty string."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST=''
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email=self.approved_email,
                subject=self.subject,
                html_content=self.html
            )
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')

    def test_staging_with_missing_allowlist_fails_closed(self):
        """Staging fails closed if STAGING_EMAIL_ALLOWLIST is None or missing."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST=None
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email=self.approved_email,
                subject=self.subject,
                html_content=self.html
            )
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')

    def test_email_case_normalization(self):
        """Recipients and allowlist entries are normalized to lower-case without case-sensitivity mismatch."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='Approved.Tester@StrideID.COM'
        ):
            # Mixed-case recipient
            res1 = BrevoEmailService.send_transactional_email(
                to_email="approved.tester@strideid.com",
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res1.get('success'))

            # UPPERCASE recipient
            res2 = BrevoEmailService.send_transactional_email(
                to_email="APPROVED.TESTER@STRIDEID.COM",
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res2.get('success'))

    def test_domain_wildcard_allowlist(self):
        """Allowlist with domain pattern (@domain.com) permits any address on that domain."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='@strideid.com,founder@partner.ng'
        ):
            res1 = BrevoEmailService.send_transactional_email(
                to_email="alex.dev@strideid.com",
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res1.get('success'))

            res2 = BrevoEmailService.send_transactional_email(
                to_email="founder@partner.ng",
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res2.get('success'))

            # Outside domain is blocked
            res3 = BrevoEmailService.send_transactional_email(
                to_email="intruder@partner.ng",
                subject=self.subject,
                html_content=self.html
            )
            self.assertFalse(res3.get('success'))
            self.assertEqual(res3.get('mode'), 'blocked_staging')

    def test_multiple_recipients_allowed_when_all_approved(self):
        """Multiple recipients are permitted when all are allowlisted."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='tester1@strideid.com,tester2@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email=["tester1@strideid.com", "tester2@strideid.com"],
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res.get('success'))

    def test_multiple_recipients_blocked_if_any_unapproved(self):
        """Multiple recipients dispatch is blocked if even one recipient is unapproved."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='tester1@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email=["tester1@strideid.com", "unapproved@other.com"],
                subject=self.subject,
                html_content=self.html
            )
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')
            self.assertIn("STAGING_EMAIL_ALLOWLIST", res.get('error'))
            self.assertNotIn("unapproved@other.com", res.get('error'))

    def test_cc_and_bcc_handling_blocked_when_unapproved(self):
        """CC or BCC containing unapproved recipients causes the entire dispatch to be blocked."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='primary@strideid.com'
        ):
            # Unapproved CC
            res_cc = BrevoEmailService.send_transactional_email(
                to_email="primary@strideid.com",
                subject=self.subject,
                html_content=self.html,
                cc=["unapproved_cc@gmail.com"]
            )
            self.assertFalse(res_cc.get('success'))
            self.assertEqual(res_cc.get('mode'), 'blocked_staging')
            self.assertIn("STAGING_EMAIL_ALLOWLIST", res_cc.get('error'))
            self.assertNotIn("unapproved_cc@gmail.com", res_cc.get('error'))

            # Unapproved BCC
            res_bcc = BrevoEmailService.send_transactional_email(
                to_email="primary@strideid.com",
                subject=self.subject,
                html_content=self.html,
                bcc=["unapproved_bcc@gmail.com"]
            )
            self.assertFalse(res_bcc.get('success'))
            self.assertEqual(res_bcc.get('mode'), 'blocked_staging')
            self.assertIn("STAGING_EMAIL_ALLOWLIST", res_bcc.get('error'))
            self.assertNotIn("unapproved_bcc@gmail.com", res_bcc.get('error'))

    def test_cc_and_bcc_handling_allowed_when_approved(self):
        """CC and BCC are permitted when all addresses are allowlisted."""
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='primary@strideid.com,cc@strideid.com,bcc@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email="primary@strideid.com",
                subject=self.subject,
                html_content=self.html,
                cc="cc@strideid.com",
                bcc="bcc@strideid.com"
            )
            self.assertTrue(res.get('success'))

    def test_blocked_log_does_not_expose_pii(self):
        """Confirm blocked logs do not expose recipient addresses, subjects, or message bodies."""
        sensitive_recipient = "sensitive_customer@external.com"
        sensitive_subject = "CONFIDENTIAL: Your Invoice #98765"
        sensitive_body = "<p>Sensitive confidential information</p>"

        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='authorized@strideid.com'
        ):
            with self.assertLogs('stride.email_service', level='WARNING') as cm:
                res = BrevoEmailService.send_transactional_email(
                    to_email=sensitive_recipient,
                    subject=sensitive_subject,
                    html_content=sensitive_body
                )

            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')
            self.assertEqual(res.get('status'), 'blocked_staging')

            # Ensure identifier is present
            self.assertTrue(any("[STAGING EMAIL BLOCKED]" in log for log in cm.output))

            # Ensure no PII (email, subject, body) appears in warning logs
            for log in cm.output:
                self.assertNotIn(sensitive_recipient, log)
                self.assertNotIn(sensitive_subject, log)
                self.assertNotIn("Sensitive confidential", log)

            # Ensure returned error message does not expose recipient address
            self.assertNotIn(sensitive_recipient, res.get('error'))
            self.assertNotIn(sensitive_subject, res.get('error'))

    def test_production_behavior_remains_unchanged(self):
        """In production environment, unlisted external recipients are not blocked by staging allowlist."""
        with self.settings(
            ENVIRONMENT='production',
            STAGING_EMAIL_ALLOWLIST='someone_else@strideid.com'
        ):
            # In production, dispatch proceeds normally without staging allowlist block
            res = BrevoEmailService.send_transactional_email(
                to_email="customer@anydomain.com",
                subject=self.subject,
                html_content=self.html
            )
            # In test environment, it falls back to simulated
            self.assertTrue(res.get('success'))
            self.assertNotEqual(res.get('mode'), 'blocked_staging')

    @patch('apps.core.services.email_service.requests.post')
    def test_blocked_emails_never_reach_brevo_api(self, mock_post):
        """When an email is blocked by the staging allowlist, no HTTP request is made to Brevo API."""
        with self.settings(
            ENVIRONMENT='staging',
            DEBUG=False,
            BREVO_API_KEY='xkeysib-live-mock-api-key',
            BREVO_SENDER_EMAIL='notifications@strideid.com',
            STAGING_EMAIL_ALLOWLIST='authorized@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email="leak_target@external.com",
                subject=self.subject,
                html_content=self.html
            )
            self.assertFalse(res.get('success'))
            self.assertEqual(res.get('mode'), 'blocked_staging')
            mock_post.assert_not_called()

    @patch('apps.core.services.email_service.requests.post')
    def test_approved_staging_emails_reach_brevo_api(self, mock_post):
        """When in staging with live config, an approved email makes the HTTP request to Brevo API."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<staging-test-msg-123>"}
        mock_post.return_value = mock_response

        with self.settings(
            ENVIRONMENT='staging',
            DEBUG=False,
            BREVO_API_KEY='xkeysib-live-mock-api-key',
            BREVO_SENDER_EMAIL='notifications@strideid.com',
            EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
            STAGING_EMAIL_ALLOWLIST='authorized@strideid.com'
        ):
            res = BrevoEmailService.send_transactional_email(
                to_email="authorized@strideid.com",
                subject=self.subject,
                html_content=self.html
            )
            self.assertTrue(res.get('success'))
            self.assertEqual(res.get('mode'), 'live')
            self.assertEqual(res.get('message_id'), '<staging-test-msg-123>')
            self.assertEqual(mock_post.call_count, 1)


class BrevoCallerResilienceTests(TestCase):
    """
    Verifies that all application callers handle a blocked staging email safely
    without unhandled exceptions or broken user workflows.
    """

    def setUp(self):
        self.client = Client()

    def test_registration_view_handles_blocked_welcome_email(self):
        """User registration in staging with unapproved email completes registration safely with warning."""
        url = reverse('accounts:register')
        payload = {
            'first_name': 'Blocked',
            'last_name': 'Tester',
            'email': 'unapproved_user@external.com',
            'password': 'StrongPassword123!',
            'password_confirm': 'StrongPassword123!',
            'agree_terms': True,
        }

        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='team@strideid.com'
        ):
            response = self.client.post(url, payload, follow=True)
            self.assertEqual(response.status_code, 200)

            # Confirm user was created in database
            user = User.objects.filter(email='unapproved_user@external.com').first()
            self.assertIsNotNone(user)
            self.assertFalse(user.is_email_verified)

            # Confirm user is redirected to verify_otp
            self.assertIn(reverse('accounts:verify_otp'), response.request['PATH_INFO'])

            # Confirm warning flash message about email delivery
            messages = list(response.context['messages'])
            self.assertTrue(any("could not deliver your verification code email" in m.message.lower() for m in messages))

    def test_resend_otp_handles_blocked_email(self):
        """Resend OTP in staging with unapproved email fails gracefully with warning message."""
        user = User.objects.create_user(
            email='unapproved_resend@external.com',
            password='Password123!',
            first_name='Resend',
            last_name='User'
        )
        self.client.force_login(user)
        session = self.client.session
        session['pending_verification_email'] = user.email
        session.save()

        url = reverse('accounts:resend_otp')
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='team@strideid.com'
        ):
            response = self.client.post(url, follow=True)
            self.assertEqual(response.status_code, 200)

            messages = list(response.context['messages'])
            self.assertTrue(any("could not deliver your verification email" in m.message.lower() for m in messages))

    def test_password_reset_handles_blocked_email(self):
        """Password reset in staging with unapproved email displays generic success without crashing."""
        user = User.objects.create_user(
            email='unapproved_reset@external.com',
            password='Password123!',
            first_name='Reset',
            last_name='User'
        )
        url = reverse('accounts:password_reset')
        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='team@strideid.com'
        ):
            response = self.client.post(url, {'email': user.email}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Check your email inbox")

    def test_order_and_payment_caller_methods_handle_blocked_email(self):
        """Higher-level transactional email wrappers return blocked result cleanly."""
        user = User.objects.create_user(
            email='unapproved_shopper@external.com',
            password='Password123!',
            first_name='Shopper'
        )
        package = ProductPackage.objects.create(
            code='standard-nfc-email-test',
            name='Standard NFC Card',
            package_type='card_only',
            price_ngn=15000,
            is_active=True
        )
        order = Order.objects.create(
            user=user,
            package=package,
            amount=15000,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED,
        )
        payment = Payment.objects.create(
            order=order,
            reference="STR-EMAIL-TEST-001",
            amount=15000,
            provider='paystack',
            status=Payment.STATUS_PENDING,
        )
        card = Card.objects.create(
            card_code="ST-EMAIL-001",
            status=Card.STATUS_ACTIVE,
            user=user
        )

        with self.settings(
            ENVIRONMENT='staging',
            STAGING_EMAIL_ALLOWLIST='team@strideid.com'
        ):
            # Order confirmation
            res_order = BrevoEmailService.send_order_confirmation_email(order)
            self.assertFalse(res_order.get('success'))
            self.assertEqual(res_order.get('mode'), 'blocked_staging')

            # Payment confirmation
            res_pay = BrevoEmailService.send_payment_confirmation_email(payment)
            self.assertFalse(res_pay.get('success'))
            self.assertEqual(res_pay.get('mode'), 'blocked_staging')

            # Card activation
            res_card = BrevoEmailService.send_card_activation_notification(user, card)
            self.assertFalse(res_card.get('success'))
            self.assertEqual(res_card.get('mode'), 'blocked_staging')
