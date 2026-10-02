from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.profiles.models import Profile
from apps.cards.models import Card, CardEvent
from apps.orders.models import ProductPackage, Order
from apps.payments.models import Payment
from apps.analytics.models import AnalyticsEvent
from apps.core.models import BusinessInquiry

User = get_user_model()

class PlatformCoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='TestPassword123!',
            first_name='Test',
            last_name='User'
        )
        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
            defaults={
                'slug': 'test-user',
                'full_name': 'Test User',
                'phone': '+2348012345678',
                'whatsapp': '+2348012345678',
                'email': 'testuser@example.com'
            }
        )
        self.active_card = Card.objects.create(
            card_code='BR-999001',
            user=self.user,
            profile=self.profile,
            status=Card.STATUS_ACTIVE
        )
        self.lost_card = Card.objects.create(
            card_code='BR-999002',
            user=self.user,
            status=Card.STATUS_LOST
        )
        self.unassigned_card = Card.objects.create(
            card_code='BR-999003',
            status=Card.STATUS_UNASSIGNED
        )
        self.package = ProductPackage.objects.create(
            code='test-card-pkg',
            name='Test Smart Card',
            package_type='card_only',
            price_ngn=25000,
            description='Test card description',
            features='Feature 1\nFeature 2'
        )

    def test_homepage_renders(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'YOUR IDENTITY. YOUR BUSINESS. ONE TOUCH.')

    def test_pricing_renders_packages(self):
        response = self.client.get(reverse('core:pricing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Smart Card')

    def test_nfc_active_card_redirects_to_profile(self):
        """Active card /c/BR-999001/ must redirect to /u/test-user/ and log events."""
        response = self.client.get(f'/c/{self.active_card.card_code}/', follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.profile.slug, response.url)

        # Check event logged
        self.assertTrue(CardEvent.objects.filter(card=self.active_card).exists())
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile).exists())

    def test_nfc_lost_card_renders_security_notice(self):
        response = self.client.get(f'/c/{self.lost_card.card_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Card Inactive')
        self.assertContains(response, 'reported lost')

    def test_nfc_unassigned_card_renders_activation_page(self):
        response = self.client.get(f'/c/{self.unassigned_card.card_code}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activate Smart Card')

    def test_public_profile_and_vcard_generation(self):
        # Public Profile HTML
        response = self.client.get(reverse('profiles:public_profile', kwargs={'slug': self.profile.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test User')

        # Download vCard .vcf
        vcard_response = self.client.get(reverse('profiles:download_vcard', kwargs={'slug': self.profile.slug}))
        self.assertEqual(vcard_response.status_code, 200)
        self.assertEqual(vcard_response['Content-Type'], 'text/vcard; charset=utf-8')
        self.assertIn('BEGIN:VCARD', vcard_response.content.decode('utf-8'))
        self.assertIn('FN:Test User', vcard_response.content.decode('utf-8'))

    def test_customer_registration_creates_profile(self):
        reg_data = {
            'first_name': 'New',
            'last_name': 'Customer',
            'email': 'newcustomer@example.com',
            'phone': '+2348099887766',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'agree_terms': 'on',
        }
        response = self.client.post(reverse('accounts:register'), reg_data, follow=True)
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(email='newcustomer@example.com')
        self.assertIsNotNone(new_user.profile)
        self.assertEqual(new_user.profile.full_name, 'New Customer')

    @override_settings(PAYSTACK_TEST_MODE=True)
    def test_order_creation_and_payment_simulation(self):
        self.client.force_login(self.user)
        checkout_data = {
            'shipping_name': 'Test User',
            'shipping_phone': '+2348012345678',
            'shipping_address': '123 Test Street',
            'shipping_city': 'Lagos',
            'shipping_state': 'Lagos State',
        }
        response = self.client.post(reverse('orders:checkout', kwargs={'package_code': self.package.code}), checkout_data, follow=True)
        self.assertEqual(response.status_code, 200)

        order = Order.objects.filter(user=self.user).latest('created_at')
        self.assertEqual(order.package, self.package)
        self.assertEqual(order.amount, 25000)

        # Payment verification simulator
        payment = Payment.objects.create(
            order=order,
            reference=f"REF-{order.order_number}",
            amount=order.amount
        )
        verify_response = self.client.post(reverse('payments:verify'), {
            'reference': payment.reference,
            'simulated': 'true'
        }, follow=True)
        self.assertEqual(verify_response.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)

    def test_analytics_api_beacon(self):
        payload = {
            'profile_slug': self.profile.slug,
            'event_type': 'whatsapp_click',
            'target_label': 'WhatsApp Chat'
        }
        response = self.client.post(
            reverse('analytics:track_event'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AnalyticsEvent.objects.filter(profile=self.profile, event_type='whatsapp_click').exists())


class BusinessInquiryTests(TestCase):
    """
    Phase 14 — Comprehensive test suite for Business & Custom Solutions inquiry system.
    """

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='staff@uzyra.com',
            password='StaffPassword123!',
            first_name='Operations',
            last_name='Admin',
            is_staff=True
        )
        self.regular_user = User.objects.create_user(
            email='customer@example.com',
            password='CustomerPassword123!',
            first_name='Regular',
            last_name='Customer',
            is_staff=False
        )
        self.inquiry = BusinessInquiry.objects.create(
            full_name='Amina Yusuf',
            company_name='Apex Security Ltd',
            email='amina@apexsec.ng',
            phone='+2348031234567',
            business_type=BusinessInquiry.TYPE_SECURITY,
            service_type=BusinessInquiry.SERVICE_SECURITY,
            estimated_card_quantity='50-100',
            needs_website=True,
            message='We need NFC cards for our patrol officers across Abuja.',
            ip_address='127.0.0.1'
        )

    def test_business_page_renders_cleanly(self):
        response = self.client.get(reverse('core:business'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Built for more')
        self.assertContains(response, 'Company &amp; Teams')
        self.assertContains(response, 'Talk to UZYRA')
        self.assertContains(response, 'Prefer WhatsApp?')

    def test_business_inquiry_submission_success(self):
        post_data = {
            'full_name': 'Chidi Okafor',
            'company_name': 'Horizon Events',
            'email': 'chidi@horizonevents.ng',
            'phone': '+2348098765432',
            'business_type': BusinessInquiry.TYPE_EVENT,
            'service_type': BusinessInquiry.SERVICE_EVENT,
            'estimated_card_quantity': '200+',
            'needs_website': 'on',
            'message': 'We manage a tech conference and need NFC attendee badges.',
            'website_url_hp': '',  # Empty honeypot
        }
        response = self.client.post(reverse('core:business'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        inquiry = BusinessInquiry.objects.filter(email='chidi@horizonevents.ng').first()
        self.assertIsNotNone(inquiry)
        self.assertEqual(inquiry.full_name, 'Chidi Okafor')
        self.assertEqual(inquiry.company_name, 'Horizon Events')
        self.assertEqual(inquiry.business_type, BusinessInquiry.TYPE_EVENT)
        self.assertEqual(inquiry.service_type, BusinessInquiry.SERVICE_EVENT)
        self.assertTrue(inquiry.needs_website)
        self.assertEqual(inquiry.status, BusinessInquiry.STATUS_NEW)

    def test_business_inquiry_honeypot_trap(self):
        """Bots that fill the honeypot should be trapped with fake success without creating a record."""
        initial_count = BusinessInquiry.objects.count()
        post_data = {
            'full_name': 'Spam Bot',
            'company_name': 'Spam Corp',
            'email': 'bot@spammer.com',
            'phone': '+1234567890',
            'service_type': BusinessInquiry.SERVICE_OTHER,
            'estimated_card_quantity': '10',
            'message': 'Buy cheap crypto now!',
            'website_url_hp': 'http://spam-site.com',  # Honeypot filled!
        }
        response = self.client.post(reverse('core:business'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessInquiry.objects.count(), initial_count)
        self.assertFalse(BusinessInquiry.objects.filter(email='bot@spammer.com').exists())

    def test_business_inquiry_rate_limiting(self):
        """Should throttle when an IP makes more than 4 submissions in window."""
        post_data = {
            'full_name': 'Spammer Rate',
            'email': 'rate@example.com',
            'service_type': BusinessInquiry.SERVICE_OTHER,
            'message': 'Test rate limit message.',
        }
        # First 4 allowed (including earlier in test or loop)
        for i in range(4):
            self.client.post(reverse('core:business'), post_data, REMOTE_ADDR='198.51.100.55')

        # 5th submission should trigger rate limit message
        response = self.client.post(reverse('core:business'), post_data, REMOTE_ADDR='198.51.100.55', follow=True)
        self.assertContains(response, 'Too many submissions')

    def test_model_methods_and_properties(self):
        self.assertIn('Amina Yusuf', str(self.inquiry))
        self.assertEqual(self.inquiry.display_quantity, '50-100')
        self.assertEqual(self.inquiry.status_badge_class, 'badge-info')

        blank_inquiry = BusinessInquiry(full_name='Test', email='t@t.com', estimated_card_quantity='')
        self.assertEqual(blank_inquiry.display_quantity, 'Not specified')

    def test_operations_inquiries_list_permissions(self):
        url = reverse('operations:inquiries_list')

        # Anonymous -> redirect to login
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

        # Non-staff user -> 403 Forbidden
        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Staff user -> 200 OK
        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amina Yusuf')
        self.assertContains(response, 'Apex Security Ltd')

    def test_operations_inquiries_search_and_filters(self):
        self.client.force_login(self.staff_user)
        url = reverse('operations:inquiries_list')

        # Search by company
        response = self.client.get(f"{url}?q=Apex")
        self.assertContains(response, 'Amina Yusuf')

        # Search non-matching
        response = self.client.get(f"{url}?q=NonExistentCompany")
        self.assertNotContains(response, 'Amina Yusuf')

        # Status filter
        response = self.client.get(f"{url}?status=new")
        self.assertContains(response, 'Amina Yusuf')
        response = self.client.get(f"{url}?status=closed")
        self.assertNotContains(response, 'Amina Yusuf')

        # Business type filter
        response = self.client.get(f"{url}?business_type=security")
        self.assertContains(response, 'Amina Yusuf')
        response = self.client.get(f"{url}?business_type=retail")
        self.assertNotContains(response, 'Amina Yusuf')

    def test_operations_inquiry_detail_and_notes(self):
        self.client.force_login(self.staff_user)
        detail_url = reverse('operations:inquiry_detail', kwargs={'inquiry_id': self.inquiry.id})

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amina Yusuf')
        self.assertContains(response, 'Apex Security Ltd')

        # Save staff notes
        post_data = {
            'action': 'save_notes',
            'admin_notes': 'Called customer. Scheduled demo for Friday 2pm.'
        }
        response = self.client.post(detail_url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.admin_notes, 'Called customer. Scheduled demo for Friday 2pm.')

    def test_operations_inquiry_update_status(self):
        self.client.force_login(self.staff_user)
        update_url = reverse('operations:inquiry_update_status', kwargs={'inquiry_id': self.inquiry.id})

        # GET request not allowed (require_POST)
        get_response = self.client.get(update_url)
        self.assertEqual(get_response.status_code, 405)

        # POST valid status update
        response = self.client.post(update_url, {'status': BusinessInquiry.STATUS_CONSULTATION}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.status, BusinessInquiry.STATUS_CONSULTATION)

    def test_email_service_business_notifications(self):
        from apps.core.services.email_service import BrevoEmailService
        confirm_result = BrevoEmailService.send_business_inquiry_confirmation(self.inquiry)
        self.assertTrue(confirm_result.get('success'))

        alert_result = BrevoEmailService.send_business_inquiry_admin_alert(self.inquiry)
        self.assertTrue(alert_result.get('success'))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6 — SEO TESTS
# ─────────────────────────────────────────────────────────────────────────────
class SEOTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='seotest@example.com',
            password='TestPass123!',
            first_name='SEO',
            last_name='Test',
        )
        self.profile, _ = Profile.objects.get_or_create(
            user=self.user,
            defaults={
                'slug': 'seo-test-user',
                'full_name': 'SEO Test User',
                'is_search_indexed': True,
            }
        )

    def test_robots_txt_returns_200_text_plain(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')

    def test_robots_txt_disallows_dashboard(self):
        response = self.client.get('/robots.txt')
        content = response.content.decode()
        self.assertIn('Disallow: /dashboard/', content)
        self.assertIn('Disallow: /admin/', content)
        self.assertIn('Disallow: /operations/', content)

    def test_robots_txt_allows_public_profiles(self):
        response = self.client.get('/robots.txt')
        content = response.content.decode()
        self.assertIn('Allow: /u/', content)

    def test_robots_txt_includes_sitemap_link(self):
        response = self.client.get('/robots.txt')
        content = response.content.decode()
        self.assertIn('Sitemap:', content)
        self.assertIn('sitemap.xml', content)

    def test_sitemap_xml_returns_200(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)

    def test_public_profile_has_og_tags(self):
        response = self.client.get(f'/u/{self.profile.slug}/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('og:title', content)
        self.assertIn('og:description', content)
        self.assertIn('og:url', content)
        self.assertIn('og:type', content)
        self.assertIn('og:site_name', content)

    def test_public_profile_has_canonical_tag(self):
        response = self.client.get(f'/u/{self.profile.slug}/')
        content = response.content.decode()
        self.assertIn('rel="canonical"', content)

    def test_private_profile_has_noindex(self):
        self.profile.is_search_indexed = False
        self.profile.save()
        response = self.client.get(f'/u/{self.profile.slug}/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('noindex', content)

    def test_public_profile_no_noindex_when_indexed(self):
        self.profile.is_search_indexed = True
        self.profile.save()
        response = self.client.get(f'/u/{self.profile.slug}/')
        content = response.content.decode()
        # noindex should not be present for an indexed profile
        self.assertNotIn('noindex, nofollow', content)

    def test_base_template_has_og_blocks(self):
        """Home page (which uses base.html) should have OG meta tags."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('og:site_name', content)
        self.assertIn('og:type', content)
        self.assertIn('og:title', content)

    def test_public_profile_has_structured_data(self):
        response = self.client.get(f'/u/{self.profile.slug}/')
        content = response.content.decode()
        self.assertIn('application/ld+json', content)
        self.assertIn('"@type": "Person"', content)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7 — ORDER CONFIRMATION EMAIL WIRED
# ─────────────────────────────────────────────────────────────────────────────
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class OrderConfirmationEmailTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='orderemail@example.com',
            password='TestPass123!',
            first_name='Order',
            last_name='Email',
        )
        Profile.objects.get_or_create(
            user=self.user,
            defaults={'slug': 'order-email-user', 'full_name': 'Order Email User'}
        )
        self.package = ProductPackage.objects.create(
            name='Test Package',
            code='test_pkg',
            package_type='card_only',
            price_ngn=15000,
            is_active=True,
        )

    def test_send_order_confirmation_email_method_exists(self):
        """Email service must have the send_order_confirmation_email method."""
        from apps.core.services.email_service import BrevoEmailService
        self.assertTrue(hasattr(BrevoEmailService, 'send_order_confirmation_email'))

    def test_order_confirmation_email_returns_success_in_test_mode(self):
        """In test mode (locmem backend) the method must return a success dict."""
        from apps.core.services.email_service import BrevoEmailService
        order = Order.objects.create(
            user=self.user,
            package=self.package,
            amount=self.package.price_ngn,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED,
        )
        result = BrevoEmailService.send_order_confirmation_email(order)
        self.assertTrue(result.get('success'))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 8 — OPERATIONS ORDER DETAIL
# ─────────────────────────────────────────────────────────────────────────────
class OperationsOrderDetailTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            email='staff_order@example.com',
            password='StaffPass123!',
            first_name='Staff',
            last_name='Order',
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email='customer_order@example.com',
            password='CustPass123!',
            first_name='Customer',
            last_name='Order',
        )
        self.package = ProductPackage.objects.create(
            name='Test Ops Package',
            code='ops_test_pkg',
            package_type='card_only',
            price_ngn=20000,
            is_active=True,
        )
        self.order = Order.objects.create(
            user=self.customer,
            package=self.package,
            amount=self.package.price_ngn,
            payment_status=Order.PAYMENT_PENDING,
            order_status=Order.STATUS_RECEIVED,
        )

    def test_order_detail_requires_staff(self):
        """Non-staff users must be denied access (403)."""
        non_staff = User.objects.create_user(
            email='notstaff@example.com',
            password='Pass123!',
        )
        self.client.login(email='notstaff@example.com', password='Pass123!')
        response = self.client.get(
            reverse('operations:order_detail', kwargs={'order_number': self.order.order_number})
        )
        self.assertEqual(response.status_code, 403)

    def test_order_detail_accessible_by_staff(self):
        """Staff can access order detail page."""
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        response = self.client.get(
            reverse('operations:order_detail', kwargs={'order_number': self.order.order_number})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

    def test_order_detail_shows_package_name(self):
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        response = self.client.get(
            reverse('operations:order_detail', kwargs={'order_number': self.order.order_number})
        )
        self.assertContains(response, self.package.name)

    def test_order_detail_404_for_invalid_order(self):
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        response = self.client.get(
            reverse('operations:order_detail', kwargs={'order_number': 'INVALID-9999'})
        )
        self.assertEqual(response.status_code, 404)

    def test_update_order_status(self):
        """Staff can update order status via POST."""
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        update_url = reverse('operations:order_update_status', kwargs={'order_number': self.order.order_number})
        response = self.client.post(update_url, {
            'order_status': Order.STATUS_DESIGNING,
            'payment_status': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, Order.STATUS_DESIGNING)

    def test_update_invalid_status_rejected(self):
        """Invalid status values must be rejected."""
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        update_url = reverse('operations:order_update_status', kwargs={'order_number': self.order.order_number})
        original_status = self.order.order_status
        self.client.post(update_url, {
            'order_status': 'totally_fake_status',
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, original_status)

    def test_update_requires_post(self):
        """Update endpoint must refuse GET requests."""
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        update_url = reverse('operations:order_update_status', kwargs={'order_number': self.order.order_number})
        response = self.client.get(update_url)
        self.assertEqual(response.status_code, 405)

    def test_orders_list_links_to_detail(self):
        """The orders list template must contain a link to the order detail page."""
        self.client.login(email='staff_order@example.com', password='StaffPass123!')
        response = self.client.get(reverse('operations:orders_list'))
        self.assertEqual(response.status_code, 200)
        detail_url = reverse('operations:order_detail', kwargs={'order_number': self.order.order_number})
        self.assertContains(response, detail_url)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 9 — NFC CARD SECURITY / IDOR VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
class CardSecurityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='usera_card@example.com',
            password='PassA123!',
            first_name='User',
            last_name='A',
        )
        self.user_b = User.objects.create_user(
            email='userb_card@example.com',
            password='PassB123!',
            first_name='User',
            last_name='B',
        )
        Profile.objects.get_or_create(
            user=self.user_a,
            defaults={'slug': 'usera-card', 'full_name': 'User A'}
        )
        Profile.objects.get_or_create(
            user=self.user_b,
            defaults={'slug': 'userb-card', 'full_name': 'User B'}
        )
        self.card = Card.objects.create(
            card_code='BR-TEST-IDOR',
            status=Card.STATUS_ACTIVE,
            user=self.user_a,
        )

    def test_card_cannot_be_reported_lost_by_another_user(self):
        """User B must not be able to report User A's card as lost (IDOR)."""
        self.client.login(email='userb_card@example.com', password='PassB123!')
        response = self.client.post(
            reverse('cards:card_report_lost', kwargs={'card_id': self.card.id}),
        )
        # Must return 404 (card is not owned by User B)
        self.assertEqual(response.status_code, 404)
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_ACTIVE)

    def test_nfc_redirect_active_card_redirects_to_profile(self):
        """An active card tap must redirect to the owner's public profile."""
        profile_a = Profile.objects.get(user=self.user_a)
        self.card.profile = profile_a
        self.card.save()
        response = self.client.get(f'/c/{self.card.card_code}/')
        self.assertRedirects(
            response,
            f'/u/{profile_a.slug}/',
            fetch_redirect_response=False,
        )

    def test_nfc_redirect_unknown_card_returns_404(self):
        response = self.client.get('/c/NONEXISTENT-CARD/')
        self.assertEqual(response.status_code, 404)

    def test_nfc_redirect_lost_card_does_not_redirect_to_profile(self):
        """A lost card must not route to the owner's profile."""
        self.card.status = Card.STATUS_LOST
        self.card.save()
        response = self.client.get(f'/c/{self.card.card_code}/')
        # Must NOT be a redirect to the profile
        self.assertNotEqual(response.status_code, 302)

    def test_operations_card_suspend_requires_staff(self):
        """Non-staff users cannot suspend cards via operations."""
        self.client.login(email='usera_card@example.com', password='PassA123!')
        response = self.client.post(
            reverse('operations:card_suspend', kwargs={'card_id': self.card.id}),
        )
        self.assertEqual(response.status_code, 403)
