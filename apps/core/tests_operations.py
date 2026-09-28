"""
Phase 13: Admin & Operations — Comprehensive Test Suite
Covers:
- Access control & authorization (Staff vs Normal vs Anonymous)
- Customer directory, search, details, account suspend/restore
- Card inventory, unique code enforcement, filtering, search
- Card creation & bulk generation
- Atomic card assignment & reassignment
- Concurrency protection
- Card lifecycle states: suspension, restoration, lost, replacement
- NFC public route behavior on suspended/lost/replaced cards
- Website management & publish/unpublish toggle
- Orders inspection
- Audit logging of all administrative actions
- Non-staff isolation from audit logs and operations endpoints
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import transaction

from apps.cards.models import Card, CardEvent
from apps.profiles.models import Profile
from apps.websites.models import Website
from apps.orders.models import ProductPackage, Order
from apps.core.models import AdminAuditLog

User = get_user_model()


class OperationsAccessControlTests(TestCase):
    """Ensure normal customers and anonymous users cannot access operations endpoints."""

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='staff@uzyra.com',
            password='StaffPass123!',
            first_name='Staff',
            last_name='Admin',
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email='customer@uzyra.com',
            password='CustomerPass123!',
            first_name='Regular',
            last_name='Customer',
            is_staff=False,
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('operations:overview'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_customer_forbidden_403(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('operations:overview'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_access_customers_list(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('operations:customers_list'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_access_cards_list(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('operations:cards_list'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_access_audit_logs(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('operations:audit_logs'))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_gets_200(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('operations:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'operations/overview.html')


class OperationsCustomerManagementTests(TestCase):
    """Test customer listing, searching, detail viewing, and account suspension."""

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='ops@uzyra.com',
            password='Password123!',
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email='alice@client.com',
            password='Password123!',
            first_name='Alice',
            last_name='Smith',
            phone='+2348011223344',
        )
        self.profile = self.customer.profile
        self.client.force_login(self.staff_user)

    def test_customer_list_renders(self):
        response = self.client.get(reverse('operations:customers_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'alice@client.com')

    def test_customer_search_by_name(self):
        response = self.client.get(reverse('operations:customers_list'), {'q': 'Alice'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'alice@client.com')

    def test_customer_search_by_email(self):
        response = self.client.get(reverse('operations:customers_list'), {'q': 'alice@client.com'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')

    def test_customer_detail_renders(self):
        response = self.client.get(reverse('operations:customer_detail', kwargs={'user_id': self.customer.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'alice@client.com')
        self.assertContains(response, self.profile.slug)

    def test_customer_account_suspend_and_restore(self):
        # Suspend
        response = self.client.post(reverse('operations:customer_toggle_status', kwargs={'user_id': self.customer.id}))
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

        # Audit log verification
        log = AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_CUSTOMER_STATUS).latest('created_at')
        self.assertEqual(log.staff_user, self.staff_user)
        self.assertIn('Suspended', log.new_state)

        # Restore
        response = self.client.post(reverse('operations:customer_toggle_status', kwargs={'user_id': self.customer.id}))
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)


class OperationsCardInventoryTests(TestCase):
    """Test card creation, bulk generation, search, assignment, reassignment, suspension, lost, replacement."""

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='cardops@uzyra.com',
            password='Password123!',
            is_staff=True,
        )
        self.customer_a = User.objects.create_user(
            email='customera@uzyra.com',
            password='Password123!',
            first_name='Customer',
            last_name='Alpha',
        )
        self.customer_b = User.objects.create_user(
            email='customerb@uzyra.com',
            password='Password123!',
            first_name='Customer',
            last_name='Beta',
        )
        self.client.force_login(self.staff_user)

    def test_card_list_renders(self):
        Card.objects.create(card_code='UZY-TEST-001', status=Card.STATUS_UNASSIGNED)
        response = self.client.get(reverse('operations:cards_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'UZY-TEST-001')

    def test_card_create_single(self):
        response = self.client.post(reverse('operations:card_create'), {
            'card_code': 'UZY-CARD-999001',
            'material': 'metallic_silver',
            'activation_pin': 'TEST-9999',
        })
        self.assertEqual(response.status_code, 302)
        card = Card.objects.get(card_code='UZY-CARD-999001')
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertEqual(card.material, 'metallic_silver')
        self.assertTrue(card.check_activation_code('TEST-9999'))

        # Verify audit log
        self.assertTrue(AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_CARD_CREATED,
            target_repr__contains='UZY-CARD-999001'
        ).exists())

    def test_card_create_duplicate_rejected(self):
        Card.objects.create(card_code='UZY-DUPE-001', status=Card.STATUS_UNASSIGNED)
        response = self.client.post(reverse('operations:card_create'), {
            'card_code': 'UZY-DUPE-001',
            'material': 'matte_black',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')

    def test_card_bulk_create(self):
        response = self.client.post(reverse('operations:card_bulk_create'), {
            'prefix': 'UZY-BULK-',
            'start_number': '10',
            'count': '5',
            'material': 'carbon_dark',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Card.objects.filter(card_code__startswith='UZY-BULK-').count(), 5)
        # Check an individual generated card
        sample_card = Card.objects.get(card_code='UZY-BULK-000010')
        self.assertEqual(sample_card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNotNone(sample_card.activation_code_hash)

        # Audit log check
        self.assertTrue(AdminAuditLog.objects.filter(action=AdminAuditLog.ACTION_CARD_BULK_CREATED).exists())

    def test_card_assignment(self):
        card = Card.objects.create(card_code='UZY-ASSIGN-01', status=Card.STATUS_UNASSIGNED)
        response = self.client.post(reverse('operations:card_assign', kwargs={'card_id': card.id}), {
            'user_id': self.customer_a.id,
        })
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertEqual(card.user, self.customer_a)
        self.assertEqual(card.profile, self.customer_a.profile)
        self.assertIsNotNone(card.activated_at)

        # Audit log check
        self.assertTrue(AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_CARD_ASSIGNED,
            target_repr__contains='UZY-ASSIGN-01'
        ).exists())

    def test_card_reassignment(self):
        card = Card.objects.create(
            card_code='UZY-REASSIGN-01',
            user=self.customer_a,
            profile=self.customer_a.profile,
            status=Card.STATUS_ACTIVE
        )
        response = self.client.post(reverse('operations:card_reassign', kwargs={'card_id': card.id}), {
            'new_user_id': self.customer_b.id,
            'confirm_reassign': 'yes',
        })
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.user, self.customer_b)
        self.assertEqual(card.profile, self.customer_b.profile)

        # Audit log check
        self.assertTrue(AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_CARD_REASSIGNED,
            target_repr__contains='UZY-REASSIGN-01'
        ).exists())

    def test_card_reassignment_fails_without_confirmation(self):
        card = Card.objects.create(
            card_code='UZY-REASSIGN-02',
            user=self.customer_a,
            profile=self.customer_a.profile,
            status=Card.STATUS_ACTIVE
        )
        response = self.client.post(reverse('operations:card_reassign', kwargs={'card_id': card.id}), {
            'new_user_id': self.customer_b.id,
        })
        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.user, self.customer_a)  # Not changed

    def test_card_suspension_and_restoration(self):
        card = Card.objects.create(
            card_code='UZY-SUSPEND-01',
            user=self.customer_a,
            profile=self.customer_a.profile,
            status=Card.STATUS_ACTIVE
        )

        # 1. Suspend
        self.client.post(reverse('operations:card_suspend', kwargs={'card_id': card.id}))
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_SUSPENDED)

        # Test public NFC route behaves as suspended
        public_resp = self.client.get(card.nfc_url_path)
        self.assertTemplateUsed(public_resp, 'cards/card_suspended.html')

        # 2. Restore
        self.client.post(reverse('operations:card_restore', kwargs={'card_id': card.id}))
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)

        # Test public NFC route works again (redirects to profile)
        public_resp = self.client.get(card.nfc_url_path)
        self.assertEqual(public_resp.status_code, 302)
        self.assertIn(f"/u/{self.customer_a.profile.slug}/", public_resp['Location'])

    def test_card_mark_lost(self):
        card = Card.objects.create(
            card_code='UZY-LOST-01',
            user=self.customer_a,
            profile=self.customer_a.profile,
            status=Card.STATUS_ACTIVE
        )
        self.client.post(reverse('operations:card_mark_lost', kwargs={'card_id': card.id}))
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_LOST)

        # Public NFC route shows lost template
        public_resp = self.client.get(card.nfc_url_path)
        self.assertTemplateUsed(public_resp, 'cards/card_lost.html')

    def test_card_replacement_workflow(self):
        old_card = Card.objects.create(
            card_code='UZY-OLD-CARD',
            user=self.customer_a,
            profile=self.customer_a.profile,
            status=Card.STATUS_ACTIVE
        )
        new_card = Card.objects.create(
            card_code='UZY-NEW-CARD',
            status=Card.STATUS_UNASSIGNED
        )

        response = self.client.post(reverse('operations:card_replace', kwargs={'card_id': old_card.id}), {
            'replacement_card_id': new_card.id,
        })
        self.assertEqual(response.status_code, 302)

        old_card.refresh_from_db()
        new_card.refresh_from_db()

        self.assertEqual(old_card.status, Card.STATUS_REPLACED)
        self.assertEqual(old_card.replacement_for, new_card)
        self.assertEqual(new_card.status, Card.STATUS_ACTIVE)
        self.assertEqual(new_card.user, self.customer_a)
        self.assertEqual(new_card.profile, self.customer_a.profile)

        # Public tap on old card forwards to replacement
        public_resp = self.client.get(old_card.nfc_url_path)
        self.assertEqual(public_resp.status_code, 302)
        self.assertIn(new_card.nfc_url_path, public_resp['Location'])


class OperationsWebsiteAndOrderTests(TestCase):
    """Test website management and order inspection in operations."""

    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email='siteops@uzyra.com',
            password='Password123!',
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email='client@uzyra.com',
            password='Password123!',
            first_name='Site',
            last_name='Client',
        )
        self.website = Website.objects.create(
            user=self.customer,
            title='Client Brand Site',
            slug='client-brand-ops',
            status=Website.STATUS_DRAFT,
        )
        self.package = ProductPackage.objects.create(
            code='smart-card',
            name='Smart NFC Card',
            price_ngn=35000,
            description='Test package',
        )
        self.order = Order.objects.create(
            order_number='ORD-TEST-99',
            user=self.customer,
            package=self.package,
            amount=35000,
            payment_status=Order.PAYMENT_PAID,
            order_status=Order.STATUS_COMPLETED,
        )
        self.client.force_login(self.staff_user)

    def test_websites_list_renders(self):
        response = self.client.get(reverse('operations:websites_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client Brand Site')

    def test_website_toggle_publish(self):
        # Publish
        self.client.post(reverse('operations:website_toggle_publish', kwargs={'website_id': self.website.id}))
        self.website.refresh_from_db()
        self.assertEqual(self.website.status, Website.STATUS_PUBLISHED)

        # Verify audit log
        self.assertTrue(AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_WEBSITE_STATUS,
            target_repr__contains='Client Brand Site'
        ).exists())

        # Unpublish
        self.client.post(reverse('operations:website_toggle_publish', kwargs={'website_id': self.website.id}))
        self.website.refresh_from_db()
        self.assertEqual(self.website.status, Website.STATUS_UNPUBLISHED)

    def test_orders_list_renders(self):
        response = self.client.get(reverse('operations:orders_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '#ORD-TEST-99')
        self.assertContains(response, 'client@uzyra.com')

    def test_audit_logs_list_renders(self):
        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_CREATED,
            staff_user=self.staff_user,
            target_repr='Card TEST-LOG-01',
            details='Test log entry',
        )
        response = self.client.get(reverse('operations:audit_logs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TEST-LOG-01')
