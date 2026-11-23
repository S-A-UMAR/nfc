from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from apps.cards.models import Card
from apps.profiles.models import Profile
from apps.core.models import AdminAuditLog
from apps.orders.models import Order, ProductPackage

User = get_user_model()


class OpenCardDistributionAndActivationTests(TestCase):
    """
    Test suite for STRIDE Open Card Distribution & Activation:
    - Release for Activation & Recall to Warehouse console operations
    - Physical hardware QA guards and PIN requirements
    - Staff authorization and AdminAuditLog tracking
    - Open activation of unassigned cards by any eligible authenticated customer
    - Permanent ownership on first activation and rejection of second claims
    - Assigned-card customer restriction and warehouse stock protection
    """

    def setUp(self):
        cache.clear()
        # Staff user with console permissions
        self.staff_user = User.objects.create_user(
            email='ops_staff@stride.local',
            password='StaffPassword123!',
            first_name='Ops',
            last_name='Engineer',
            is_staff=True,
            is_active=True
        )

        # Non-staff customer 1
        self.customer_1 = User.objects.create_user(
            email='customer1@example.com',
            password='CustomerPassword123!',
            first_name='Kola',
            last_name='Adeleke',
            is_active=True
        )
        self.profile_1, _ = Profile.objects.get_or_create(
            user=self.customer_1,
            defaults={'full_name': 'Kola Adeleke', 'title': 'Product Designer'}
        )

        # Non-staff customer 2
        self.customer_2 = User.objects.create_user(
            email='customer2@example.com',
            password='CustomerPassword123!',
            first_name='Tunde',
            last_name='Bello',
            is_active=True
        )
        self.profile_2, _ = Profile.objects.get_or_create(
            user=self.customer_2,
            defaults={'full_name': 'Tunde Bello', 'title': 'Software Engineer'}
        )

        # Standard manufactured card in warehouse stock with passed QA and valid PIN
        self.pin = 'TEST-1234'
        self.card = Card.objects.create(
            card_code='ST-DIST-001',
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=True,
            hardware_test_status=Card.HARDWARE_TEST_PASSED,
            provisioning_stage=Card.STAGE_PACKAGED,
        )
        self.card.set_activation_code(self.pin)
        self.card.save()

    def test_staff_authorization_required_for_release(self):
        """Non-staff users cannot trigger release for activation."""
        self.client.login(email=self.customer_1.email, password='CustomerPassword123!')
        url = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_release': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.card.refresh_from_db()
        self.assertTrue(self.card.is_warehouse_stock)

    def test_release_requires_passed_hardware_qa(self):
        """Card with untested or failed hardware QA cannot be released."""
        self.card.hardware_test_status = Card.HARDWARE_TEST_UNTESTED
        self.card.save()

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_release': 'yes'}, follow=True)
        self.assertEqual(response.status_code, 200)

        self.card.refresh_from_db()
        self.assertTrue(self.card.is_warehouse_stock)
        self.assertContains(response, "physical hardware verification status")

        # Also test failed QA
        self.card.hardware_test_status = Card.HARDWARE_TEST_FAILED
        self.card.save()
        response_failed = self.client.post(url, {'confirm_release': 'yes'}, follow=True)
        self.card.refresh_from_db()
        self.assertTrue(self.card.is_warehouse_stock)
        self.assertContains(response_failed, "physical hardware verification status")

    def test_release_requires_pin_configured(self):
        """Card without configured PIN cannot be released."""
        self.card.activation_code_hash = None
        self.card.save()

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_release': 'yes'}, follow=True)
        self.card.refresh_from_db()
        self.assertTrue(self.card.is_warehouse_stock)
        self.assertContains(response, "secret activation PIN is not configured")

    def test_release_requires_unassigned_card(self):
        """Cannot release card that is assigned or already active."""
        self.card.user = self.customer_1
        self.card.status = Card.STATUS_RESERVED
        self.card.save()

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_release': 'yes'}, follow=True)
        self.assertContains(response, "only unassigned cards can be released")

    def test_cannot_release_or_recall_card_linked_to_customer_order(self):
        """Card associated with an active customer order cannot be released or recalled."""
        ProductPackage.ensure_default_packages(force=True)
        package = ProductPackage.objects.first()
        order = Order.objects.create(
            user=self.customer_1,
            package=package,
            card_assigned=self.card,
            order_status=Order.STATUS_PRODUCTION,
            amount=25000,
        )

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url_release = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        res_release = self.client.post(url_release, {'confirm_release': 'yes'}, follow=True)
        self.assertContains(res_release, "linked to an existing customer order")

        # Even if released previously, recall is blocked if an order is linked
        self.card.is_warehouse_stock = False
        self.card.save()
        url_recall = reverse('console:card_recall_warehouse', kwargs={'card_id': self.card.id})
        res_recall = self.client.post(url_recall, {'confirm_recall': 'yes'}, follow=True)
        self.assertContains(res_recall, "linked to an existing customer order")

    def test_successful_release_and_audit_logging(self):
        """Staff release transitions card to activation-ready and writes audit log."""
        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_release_distribution', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_release': 'yes'}, follow=True)
        self.assertEqual(response.status_code, 200)

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_warehouse_stock)
        self.assertEqual(self.card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNone(self.card.user)
        self.assertTrue(self.card.is_activation_ready)
        self.assertEqual(self.card.distribution_status_display, 'Activation-Ready (Open)')

        # Verify audit log
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_CARD_DISTRIBUTION_CHANGED,
            target_id=str(self.card.id)
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.staff_user, self.staff_user)
        self.assertEqual(log.previous_state, 'Warehouse Stock (Locked)')
        self.assertEqual(log.new_state, 'Activation-Ready (Open)')

    def test_recall_before_activation(self):
        """Unassigned activation-ready card can be recalled to warehouse stock."""
        self.card.is_warehouse_stock = False
        self.card.save()

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_recall_warehouse', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_recall': 'yes'}, follow=True)
        self.assertEqual(response.status_code, 200)

        self.card.refresh_from_db()
        self.assertTrue(self.card.is_warehouse_stock)
        self.assertEqual(self.card.distribution_status_display, 'Warehouse Stock (Locked)')

        # Verify audit log
        log = AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_CARD_DISTRIBUTION_CHANGED,
            target_id=str(self.card.id)
        ).latest('created_at')
        self.assertEqual(log.previous_state, 'Activation-Ready (Open)')
        self.assertEqual(log.new_state, 'Warehouse Stock (Locked)')

    def test_rejection_of_recall_after_activation(self):
        """Active card cannot be recalled back to warehouse stock."""
        self.card.is_warehouse_stock = False
        self.card.status = Card.STATUS_ACTIVE
        self.card.user = self.customer_1
        self.card.activated_at = timezone.now()
        self.card.save()

        self.client.login(email=self.staff_user.email, password='StaffPassword123!')
        url = reverse('console:card_recall_warehouse', kwargs={'card_id': self.card.id})
        response = self.client.post(url, {'confirm_recall': 'yes'}, follow=True)

        self.card.refresh_from_db()
        self.assertFalse(self.card.is_warehouse_stock)
        self.assertEqual(self.card.status, Card.STATUS_ACTIVE)
        self.assertContains(response, "active or assigned cards cannot be recalled")

    def test_warehouse_card_remains_blocked_from_activation(self):
        """Card still in warehouse stock cannot be activated by any customer."""
        self.assertTrue(self.card.is_warehouse_stock)

        self.client.login(email=self.customer_1.email, password='CustomerPassword123!')
        activate_url = reverse('cards:card_activate')
        response = self.client.post(activate_url, {
            'card_code': self.card.card_code,
            'activation_code': self.pin
        }, follow=True)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_UNASSIGNED)
        self.assertIsNone(self.card.user)
        self.assertContains(response, "unallocated warehouse inventory and cannot be activated")

    def test_first_successful_open_activation(self):
        """Activation-ready card is claimed by the first authenticated user with valid PIN."""
        # Release card from warehouse
        self.card.is_warehouse_stock = False
        self.card.save()

        self.client.login(email=self.customer_1.email, password='CustomerPassword123!')
        activate_url = reverse('cards:card_activate')
        response = self.client.post(activate_url, {
            'card_code': self.card.card_code,
            'activation_code': self.pin
        }, follow=True)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_ACTIVE)
        self.assertEqual(self.card.user, self.customer_1)
        self.assertEqual(self.card.profile, self.profile_1)
        self.assertIsNotNone(self.card.activated_at)
        self.assertContains(response, f"Smart Card {self.card.card_code} is now activated")

    def test_second_account_attempting_to_claim_active_card_rejected(self):
        """Once activated, a second user cannot claim or re-activate the card."""
        # Customer 1 activates the card
        self.card.is_warehouse_stock = False
        self.card.user = self.customer_1
        self.card.profile = self.profile_1
        self.card.status = Card.STATUS_ACTIVE
        self.card.activated_at = timezone.now()
        self.card.save()

        # Customer 2 attempts to activate the same card
        self.client.login(email=self.customer_2.email, password='CustomerPassword123!')
        activate_url = reverse('cards:card_activate')
        response = self.client.post(activate_url, {
            'card_code': self.card.card_code,
            'activation_code': self.pin
        }, follow=True)

        self.card.refresh_from_db()
        self.assertEqual(self.card.user, self.customer_1)  # Ownership preserved!
        self.assertEqual(self.card.profile, self.profile_1)
        self.assertContains(response, "already active and in use")

    def test_assigned_card_ownership_restriction(self):
        """Card explicitly reserved for Customer 1 cannot be activated by Customer 2."""
        self.card.is_warehouse_stock = False
        self.card.user = self.customer_1
        self.card.profile = self.profile_1
        self.card.status = Card.STATUS_RESERVED
        self.card.save()

        # Customer 2 attempts activation
        self.client.login(email=self.customer_2.email, password='CustomerPassword123!')
        activate_url = reverse('cards:card_activate')
        res_fail = self.client.post(activate_url, {
            'card_code': self.card.card_code,
            'activation_code': self.pin
        }, follow=True)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_RESERVED)
        self.assertContains(res_fail, "already assigned to another account")

        # Customer 1 (designated owner) activates
        self.client.login(email=self.customer_1.email, password='CustomerPassword123!')
        res_ok = self.client.post(activate_url, {
            'card_code': self.card.card_code,
            'activation_code': self.pin
        }, follow=True)

        self.card.refresh_from_db()
        self.assertEqual(self.card.status, Card.STATUS_ACTIVE)
        self.assertIsNotNone(self.card.activated_at)
        self.assertContains(res_ok, "activated and linked")
