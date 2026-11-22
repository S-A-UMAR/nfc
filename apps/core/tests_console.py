from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.cards.models import Card
from apps.orders.models import Order, ProductPackage

User = get_user_model()


class ConsoleSecurityAndLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(
            email="staff@strideid.com",
            password="StaffPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        self.manager_user = User.objects.create_user(
            email="manager@strideid.com",
            password="ManagerPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="CustomerPassword123!",
            is_staff=False,
        )
        self.package = ProductPackage.objects.create(
            name="Executive Black",
            code="executive-black",
            price_ngn=25000,
            description="Smart NFC Card",
        )
        self.card = Card.objects.create(
            card_code="ST-7K9M2P4R",
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=True,
            provisioning_stage=Card.STAGE_READY,
        )
        self.card.set_activation_code("888888")
        self.card.save()

    def test_anonymous_redirected_from_console(self):
        """Unauthenticated requests are redirected to login."""
        response = self.client.get(reverse('console:overview'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_customer_forbidden_from_console(self):
        """Non-staff users are denied access with 403 Forbidden."""
        self.client.login(email="customer@example.com", password="CustomerPassword123!")
        response = self.client.get(reverse('console:overview'))
        self.assertEqual(response.status_code, 403)

    def test_staff_access_console_overview(self):
        """Staff users access console overview with 200 OK."""
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")
        response = self.client.get(reverse('console:overview'))
        self.assertEqual(response.status_code, 200)

    def test_card_assign_places_card_in_reserved_state(self):
        """
        CRITICAL ARCHITECTURAL SAFETY:
        Staff assigning a card sets STATUS_RESERVED and is_warehouse_stock=False.
        It must NEVER prematurely activate the card into STATUS_ACTIVE.
        Only customer tap and PIN verification activates the card.
        """
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")
        response = self.client.post(
            reverse('console:card_assign', kwargs={'card_id': self.card.id}),
            {'user_id': self.customer.id}
        )
        self.assertEqual(response.status_code, 302)

        self.card.refresh_from_db()
        self.assertEqual(self.card.user, self.customer)
        self.assertEqual(self.card.status, Card.STATUS_RESERVED)
        self.assertFalse(self.card.is_warehouse_stock)
        self.assertIsNone(self.card.activated_at)

    def test_order_fulfillment_assigns_card_in_reserved_state(self):
        """Order fulfillment assigns a warehouse card and puts it in STATUS_RESERVED."""
        order = Order.objects.create(
            user=self.customer,
            package=self.package,
            order_number="ORD-TEST-001",
            amount=25000,
            payment_status="paid",
            order_status="processing",
        )
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")
        response = self.client.post(
            reverse('console:order_update_status', kwargs={'order_number': order.order_number}),
            {
                'order_status': Order.STATUS_DELIVERY,
                'shipping_carrier': 'DHL Express',
                'shipping_tracking_number': 'DHL-987654321',
                'assign_card_id': self.card.id,
            }
        )
        self.assertEqual(response.status_code, 302)

        order.refresh_from_db()
        self.card.refresh_from_db()

        self.assertEqual(order.order_status, Order.STATUS_DELIVERY)
        self.assertEqual(order.shipping_carrier, "DHL Express")
        self.assertEqual(order.shipping_tracking_number, "DHL-987654321")
        self.assertEqual(order.card_assigned, self.card)

        self.assertEqual(self.card.status, Card.STATUS_RESERVED)
        self.assertFalse(self.card.is_warehouse_stock)

    def test_qr_download_endpoints(self):
        """PNG and SVG endpoints stream valid QR code assets to authenticated staff."""
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")

        png_resp = self.client.get(reverse('console:card_qr_png', kwargs={'card_id': self.card.id}))
        self.assertEqual(png_resp.status_code, 200)
        self.assertEqual(png_resp['Content-Type'], 'image/png')
        self.assertTrue(png_resp.content.startswith(b'\x89PNG'))

        svg_resp = self.client.get(reverse('console:card_qr_svg', kwargs={'card_id': self.card.id}))
        self.assertEqual(svg_resp.status_code, 200)
        self.assertIn('image/svg+xml', svg_resp['Content-Type'])
        self.assertIn(b'<svg', svg_resp.content)

    def test_packaging_pdf_download_endpoint(self):
        """Staff downloads print-ready A4 PDF for one-time packaging manifest."""
        from django.core.cache import cache
        import secrets

        token = secrets.token_urlsafe(32)
        manifest = {
            "batch_reference": "BATCH-TEST-PDF",
            "staff_email": "staff@strideid.com",
            "cards": [
                {
                    "card_id": self.card.id,
                    "card_code": self.card.card_code,
                    "pin": "123456",
                    "material": "Matte Black",
                    "created_at": "2026-11-21 12:00 UTC",
                }
            ],
        }
        cache.set(f"packaging_manifest:{token}", manifest, timeout=900)

        # Authenticated staff downloads PDF
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")
        resp = self.client.get(reverse('console:packaging_pdf', kwargs={'token': token}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn('STRIDE_SLIPS_BATCH-TEST-PDF.pdf', resp['Content-Disposition'])
        self.assertTrue(resp.content.startswith(b'%PDF-'))
        self.assertEqual(resp['Cache-Control'], 'no-cache, no-store, must-revalidate, private')

        # Customer is denied
        self.client.login(email="customer@example.com", password="CustomerPassword123!")
        resp_cust = self.client.get(reverse('console:packaging_pdf', kwargs={'token': token}))
        self.assertEqual(resp_cust.status_code, 403)

    def test_batches_list_and_detail_views(self):
        """Tests the production batches hub list, search, and detail views."""
        self.card.batch_reference = "BATCH-UNIT-001"
        self.card.save(update_fields=['batch_reference'])

        self.client.login(email="staff@strideid.com", password="StaffPassword123!")

        # 1. Batches List View
        resp_list = self.client.get(reverse('console:batches_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, "BATCH-UNIT-001")
        self.assertContains(resp_list, "Production Batches")

        # 2. Search query filter
        resp_search = self.client.get(reverse('console:batches_list') + '?q=BATCH-UNIT')
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "BATCH-UNIT-001")

        # 3. Batch Detail View
        resp_detail = self.client.get(reverse('console:batch_detail', kwargs={'batch_reference': 'BATCH-UNIT-001'}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Provisioning Lifecycle Pipeline")
        self.assertContains(resp_detail, self.card.card_code)

    def test_batch_update_stage_and_pin_regeneration(self):
        """Tests bulk stage advancement and manager-only PIN regeneration."""
        self.card.batch_reference = "BATCH-STAGE-001"
        self.card.save(update_fields=['batch_reference'])

        # 1. Staff advances entire batch stage
        self.client.login(email="staff@strideid.com", password="StaffPassword123!")
        resp_stage = self.client.post(
            reverse('console:batch_update_stage', kwargs={'batch_reference': 'BATCH-STAGE-001'}),
            {'stage': Card.STAGE_ENCODED}
        )
        self.assertEqual(resp_stage.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.provisioning_stage, Card.STAGE_ENCODED)

        # 2. Non-manager staff denied PIN regeneration
        resp_regen_staff = self.client.post(
            reverse('console:batch_regenerate_pins', kwargs={'batch_reference': 'BATCH-STAGE-001'}),
            {'reason': 'Lost packaging slips in warehouse'}
        )
        self.assertEqual(resp_regen_staff.status_code, 403)

        # 3. Operations Manager regenerates batch PINs
        self.client.login(email="manager@strideid.com", password="ManagerPassword123!")
        resp_regen_mgr = self.client.post(
            reverse('console:batch_regenerate_pins', kwargs={'batch_reference': 'BATCH-STAGE-001'}),
            {'reason': 'Lost packaging slips in warehouse'}
        )
        self.assertEqual(resp_regen_mgr.status_code, 302)
        self.assertIn('/console/cards/packaging/', resp_regen_mgr.url)
