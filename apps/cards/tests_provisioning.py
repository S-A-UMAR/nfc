import io
import re
import zipfile
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.cards.models import Card
from apps.cards.services.card_generator import (
    STRIDE_ALPHABET,
    STRIDE_CODE_REGEX,
    generate_single_card_code,
    create_card_batch,
    generate_batch_reference,
    sanitize_csv_cell,
)
from apps.cards.services.packaging_service import (
    get_packaging_manifest,
    acknowledge_packaging_manifest,
    build_packaging_csv_content,
    regenerate_card_activation_pin,
)
from apps.cards.services.qr_service import (
    get_canonical_card_url,
    generate_qr_png_bytes,
    generate_qr_svg_bytes,
    generate_batch_manufacturing_zip,
)
from apps.core.models import AdminAuditLog
from django.core.cache import cache

User = get_user_model()


class CardProvisioningEngineTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff_user = User.objects.create_user(
            email="staff@strideid.com",
            password="TestPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        self.manager_user = User.objects.create_user(
            email="manager@strideid.com",
            password="TestPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            password="CustomerPassword123!",
            is_staff=False,
        )

    def test_canonical_card_code_format(self):
        """Generates ST-XXXXXXXX with 8 Crockford Base32 characters."""
        code = generate_single_card_code()
        self.assertTrue(re.match(STRIDE_CODE_REGEX, code))
        self.assertTrue(code.startswith("ST-"))
        self.assertEqual(len(code), 11)  # 'ST-' (3) + 8 chars = 11
        for ch in code[3:]:
            self.assertIn(ch, STRIDE_ALPHABET)

    def test_batch_generation_creates_unassigned_warehouse_stock(self):
        """Batch generation creates cards with warehouse stock and valid hashed PINs."""
        batch_ref = generate_batch_reference()
        cards, token = create_card_batch(
            count=5,
            material="matte_black",
            batch_reference=batch_ref,
            staff_user=self.staff_user,
            ip_address="127.0.0.1",
        )
        self.assertEqual(len(cards), 5)
        self.assertIsNotNone(token)

        for card in cards:
            card.refresh_from_db()
            self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
            self.assertTrue(card.is_warehouse_stock)
            self.assertEqual(card.provisioning_stage, Card.STAGE_GENERATED)
            self.assertEqual(card.batch_reference, batch_ref)
            self.assertTrue(bool(card.activation_code_hash))
            self.assertFalse(hasattr(card, 'activation_pin'))  # no plaintext PIN on model

    def test_packaging_manifest_lifecycle_and_purge(self):
        """Manifest holds credentials in cache and purges immediately upon acknowledgement."""
        cards, token = create_card_batch(
            count=3,
            material="metallic_silver",
            batch_reference="TEST-BATCH-001",
            staff_user=self.staff_user,
        )
        manifest = get_packaging_manifest(token)
        self.assertIsNotNone(manifest)
        self.assertEqual(len(manifest['cards']), 3)

        # Check CSV generation and formula injection defense
        csv_text = build_packaging_csv_content(manifest)
        self.assertIn("Card_Code", csv_text)
        self.assertIn("Activation_PIN", csv_text)
        for item in manifest['cards']:
            self.assertIn(item['card_code'], csv_text)
            self.assertIn(item.get('pin', item.get('plaintext_pin', '')), csv_text)

        # Acknowledge and purge
        acknowledge_packaging_manifest(token)
        purged = get_packaging_manifest(token)
        self.assertIsNone(purged)

    def test_sanitize_csv_cell_prevents_injection(self):
        """Formula characters (=, +, -, @) are sanitized with leading single quote."""
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("+cmd"), "'+cmd")
        self.assertEqual(sanitize_csv_cell("-calc"), "'-calc")
        self.assertEqual(sanitize_csv_cell("@SUM"), "'@SUM")
        self.assertEqual(sanitize_csv_cell("ST-7K9M2P4R"), "ST-7K9M2P4R")

    def test_emergency_pin_regeneration(self):
        """Emergency PIN regeneration updates hash, invalidates old PIN, and audits."""
        card = Card.objects.create(
            card_code="ST-TESTPIN1",
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=True,
        )
        card.set_activation_code("111111")
        card.save()
        old_hash = card.activation_code_hash

        card, new_pin, token = regenerate_card_activation_pin(
            card_id=card.id,
            staff_user=self.manager_user,
            reason="Damaged packaging insert in warehouse",
            ip_address="127.0.0.1",
        )
        card.refresh_from_db()

        self.assertNotEqual(card.activation_code_hash, old_hash)
        self.assertTrue(card.check_activation_code(new_pin))
        self.assertFalse(card.check_activation_code("111111"))

        # Verify audit log recorded without leaking plaintext PIN
        log = AdminAuditLog.objects.filter(
            target_model='Card',
            target_id=str(card.id),
            action=AdminAuditLog.ACTION_PIN_REGENERATED
        ).first()
        self.assertIsNotNone(log)
        self.assertNotIn(new_pin, log.details)
        self.assertIn("Damaged packaging", log.details)

    def test_emergency_pin_regeneration_rejected_on_active_cards(self):
        """Cannot regenerate PIN on cards that are already activated."""
        card = Card.objects.create(
            card_code="ST-ACTIVE01",
            status=Card.STATUS_ACTIVE,
            user=self.customer,
            is_warehouse_stock=False,
        )
        with self.assertRaises(ValueError):
            regenerate_card_activation_pin(card_id=card.id, staff_user=self.manager_user, reason="Lost PIN")

    def test_qr_code_png_and_svg_generation(self):
        """Generates valid PNG bytes and SVG XML structure."""
        url = get_canonical_card_url("ST-8X9Y2Z3A")
        self.assertEqual(url, "https://strideid.com/c/ST-8X9Y2Z3A/")

        png_bytes = generate_qr_png_bytes("ST-8X9Y2Z3A")
        self.assertTrue(png_bytes.startswith(b'\x89PNG\r\n\x1a\n'))

        svg_bytes = generate_qr_svg_bytes("ST-8X9Y2Z3A")
        self.assertIn(b'<svg', svg_bytes)
        self.assertIn(b'</svg>', svg_bytes)

    def test_manufacturing_zip_export_content_and_zero_pin_leakage(self):
        """Manufacturing ZIP contains SVG, PNG, NFC manifest and strictly zero PINs."""
        cards, _ = create_card_batch(
            count=3,
            material="carbon_dark",
            batch_reference="MFG-ZIP-001",
            staff_user=self.staff_user,
        )
        zip_buf = generate_batch_manufacturing_zip(cards, batch_reference="MFG-ZIP-001")
        zip_file = zipfile.ZipFile(zip_buf)
        namelist = zip_file.namelist()

        # Check directory structure
        self.assertIn("nfc_encoding_manifest.csv", namelist)
        for card in cards:
            self.assertIn(f"svg/{card.card_code}.svg", namelist)
            self.assertIn(f"png/{card.card_code}.png", namelist)

        # Inspect manifest content
        manifest_csv = zip_file.read("nfc_encoding_manifest.csv").decode('utf-8')
        self.assertIn("Card_Code", manifest_csv)
        self.assertIn("NFC_Target_URL", manifest_csv)
        # CRITICAL: Verify NO plaintext PINs or PIN column in manufacturing manifest
        self.assertNotIn("PIN", manifest_csv)
        self.assertNotIn("pin", manifest_csv.lower())

    def test_reserved_card_customer_activation_lifecycle(self):
        """
        Verifies the full lifecycle:
        1. Batch generated card starts UNASSIGNED and warehouse-locked.
        2. Staff allocation sets STATUS_RESERVED, clears warehouse lock, binds customer.
        3. Wrong user cannot activate.
        4. Assigned customer activates with PIN -> transitions to STATUS_ACTIVE.
        """
        cards, token = create_card_batch(
            count=1,
            material="matte_black",
            batch_reference="E2E-TEST-001",
            staff_user=self.staff_user,
        )
        card = cards[0]
        manifest = get_packaging_manifest(token)
        pin = manifest['cards'][0]['pin']

        # 1. Initially warehouse-locked
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertTrue(card.is_warehouse_stock)

        # 2. Staff allocates card in Console
        c = Client()
        c.login(email="staff@strideid.com", password="TestPassword123!")
        resp = c.post(
            reverse('console:card_assign', kwargs={'card_id': card.id}),
            {'user_id': self.customer.id}
        )
        self.assertEqual(resp.status_code, 302)

        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)
        self.assertFalse(card.is_warehouse_stock)
        self.assertEqual(card.user, self.customer)
        self.assertIsNone(card.activated_at)

        # 3. Unauthorized third-party customer cannot activate
        other_user = User.objects.create_user(
            email="intruder@example.com",
            password="IntruderPass123!",
        )
        c_intruder = Client()
        c_intruder.login(email="intruder@example.com", password="IntruderPass123!")
        resp_intruder = c_intruder.post(
            reverse('cards:card_activate'),
            {'card_code': card.card_code, 'activation_code': pin}
        )
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)

        # 4. Assigned customer activates with PIN
        c_customer = Client()
        c_customer.login(email="customer@example.com", password="CustomerPassword123!")
        resp_activate = c_customer.post(
            reverse('cards:card_activate'),
            {'card_code': card.card_code, 'activation_code': pin}
        )
        self.assertEqual(resp_activate.status_code, 302)

        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertIsNotNone(card.activated_at)
        self.assertEqual(card.user, self.customer)

    def test_legacy_card_code_activation_compatibility(self):
        """Legacy card format (e.g. BR-123456) activates seamlessly with PIN."""
        legacy_card = Card.objects.create(
            card_code="BR-123456",
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=False,  # legacy card
        )
        legacy_card.set_activation_code("123456")
        legacy_card.save()

        c = Client()
        c.login(email="customer@example.com", password="CustomerPassword123!")
        resp = c.post(
            reverse('cards:card_activate'),
            {'card_code': "BR-123456", 'activation_code': "123456"}
        )
        self.assertEqual(resp.status_code, 302)

        legacy_card.refresh_from_db()
        self.assertEqual(legacy_card.status, Card.STATUS_ACTIVE)
        self.assertEqual(legacy_card.user, self.customer)

    def test_complete_15_step_lifecycle_end_to_end(self):
        """
        Verification Specification Section 10:
        Complete 15-step end-to-end integration test validating the entire
        STRIDE Console & Hardware Provisioning lifecycle without skipping any phase.
        """
        staff_client = Client()
        staff_client.login(email="staff@strideid.com", password="TestPassword123!")

        manager_client = Client()
        manager_client.login(email="manager@strideid.com", password="TestPassword123!")

        # Step 1: Staff generates 1 card in console
        resp_gen = staff_client.post(
            reverse('console:card_generate'),
            {'count': '1', 'material': 'matte_black', 'batch_reference': 'E2E-STEP-1'}
        )
        self.assertEqual(resp_gen.status_code, 302)
        # Extract packaging token from redirect URL
        redirect_url = resp_gen.url
        token = redirect_url.rstrip('/').split('/')[-1]
        self.assertTrue(len(token) > 20)

        # Step 2: System produces canonical ST-XXXXXXXX card and hashed PIN
        card = Card.objects.get(batch_reference='E2E-STEP-1')
        self.assertTrue(re.match(STRIDE_CODE_REGEX, card.card_code))
        self.assertEqual(card.status, Card.STATUS_UNASSIGNED)
        self.assertTrue(card.is_warehouse_stock)
        self.assertTrue(bool(card.activation_code_hash))
        self.assertEqual(card.provisioning_stage, Card.STAGE_GENERATED)

        # Step 3: Staff views and prints packaging slip
        resp_pack = staff_client.get(reverse('console:card_packaging', kwargs={'token': token}))
        self.assertEqual(resp_pack.status_code, 200)
        self.assertContains(resp_pack, card.card_code)

        manifest = get_packaging_manifest(token)
        plain_pin = manifest['cards'][0]['pin']
        self.assertContains(resp_pack, plain_pin)

        resp_print = staff_client.get(reverse('console:packaging_print', kwargs={'token': token}))
        self.assertEqual(resp_print.status_code, 200)
        self.assertContains(resp_print, card.card_code)

        # Step 4: Manager downloads restricted packaging CSV
        resp_csv = manager_client.get(reverse('console:packaging_csv', kwargs={'token': token}))
        self.assertEqual(resp_csv.status_code, 200)
        self.assertTrue(resp_csv['Content-Type'].startswith('text/csv'))
        csv_content = resp_csv.content.decode('utf-8')
        self.assertIn("Card_Code", csv_content)
        self.assertIn("Activation_PIN", csv_content)
        self.assertIn(card.card_code, csv_content)
        self.assertIn(plain_pin, csv_content)

        # Step 5: Staff downloads QR PNG and SVG
        resp_png = staff_client.get(reverse('console:card_qr_png', kwargs={'card_id': card.id}))
        self.assertEqual(resp_png.status_code, 200)
        self.assertEqual(resp_png['Content-Type'], 'image/png')
        self.assertTrue(resp_png.content.startswith(b'\x89PNG\r\n\x1a\n'))

        resp_svg = staff_client.get(reverse('console:card_qr_svg', kwargs={'card_id': card.id}))
        self.assertEqual(resp_svg.status_code, 200)
        self.assertEqual(resp_svg['Content-Type'], 'image/svg+xml')
        self.assertIn(b'<svg', resp_svg.content)

        # Step 6: Staff generates bulk batch of 5 cards
        resp_bulk = staff_client.post(
            reverse('console:card_generate'),
            {'count': '5', 'material': 'carbon_dark', 'batch_reference': 'BATCH-MFG-E2E'}
        )
        self.assertEqual(resp_bulk.status_code, 302)
        bulk_cards = Card.objects.filter(batch_reference='BATCH-MFG-E2E')
        self.assertEqual(bulk_cards.count(), 5)

        # Step 7: Staff downloads manufacturing ZIP (verifies zero PINs in CSV)
        resp_zip = staff_client.get(reverse('console:card_batch_export_zip') + '?batch=BATCH-MFG-E2E')
        self.assertEqual(resp_zip.status_code, 200)
        self.assertEqual(resp_zip['Content-Type'], 'application/zip')
        zip_file = zipfile.ZipFile(io.BytesIO(resp_zip.content))
        zip_names = zip_file.namelist()
        self.assertIn("nfc_encoding_manifest.csv", zip_names)
        manifest_text = zip_file.read("nfc_encoding_manifest.csv").decode('utf-8')
        self.assertNotIn("pin", manifest_text.lower())
        for b_card in bulk_cards:
            self.assertIn(f"svg/{b_card.card_code}.svg", zip_names)
            self.assertIn(f"png/{b_card.card_code}.png", zip_names)
            self.assertIn(b_card.card_code, manifest_text)

        # Step 8: Staff views card in console list and detail
        resp_list = staff_client.get(reverse('console:cards_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, card.card_code)

        resp_detail = staff_client.get(reverse('console:card_detail', kwargs={'card_id': card.id}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, card.card_code)

        # Step 9: Staff assigns/reserves card to customer (STATUS_RESERVED, NOT active)
        resp_assign = staff_client.post(
            reverse('console:card_assign', kwargs={'card_id': card.id}),
            {'user_id': self.customer.id}
        )
        self.assertEqual(resp_assign.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)
        self.assertFalse(card.is_warehouse_stock)
        self.assertEqual(card.user, self.customer)
        self.assertIsNone(card.activated_at)

        # Step 10: Customer signs in
        customer_client = Client()
        customer_client.login(email="customer@example.com", password="CustomerPassword123!")

        # Step 14 (Negative Security Tests): Unauthorized account & incorrect PIN rejected
        intruder = User.objects.create_user(email="hacker@example.com", password="Pass12345!")
        intruder_client = Client()
        intruder_client.login(email="hacker@example.com", password="Pass12345!")
        resp_intruder = intruder_client.post(
            reverse('cards:card_activate'),
            {'card_code': card.card_code, 'activation_code': plain_pin}
        )
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)  # Not activated by intruder

        resp_wrong_pin = customer_client.post(
            reverse('cards:card_activate'),
            {'card_code': card.card_code, 'activation_code': 'WRONGPIN'}
        )
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_RESERVED)  # Not activated with bad PIN

        # Step 11 & 12: Customer enters correct PIN -> Card becomes STATUS_ACTIVE
        resp_activate = customer_client.post(
            reverse('cards:card_activate'),
            {'card_code': card.card_code, 'activation_code': plain_pin}
        )
        self.assertEqual(resp_activate.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)
        self.assertIsNotNone(card.activated_at)
        self.assertIsNotNone(card.profile)

        # Step 13: Public NFC URL opens customer profile
        public_client = Client()
        resp_nfc = public_client.get(reverse('cards:nfc_redirect', kwargs={'card_code': card.card_code}))
        self.assertEqual(resp_nfc.status_code, 302)
        expected_profile_url = reverse('profiles:public_profile', kwargs={'slug': card.profile.slug})
        self.assertIn(expected_profile_url, resp_nfc.url)

        # Step 15: Emergency PIN regeneration invalidates old credentials
        unassigned_card = bulk_cards[0]
        resp_regen = manager_client.post(
            reverse('console:card_regenerate_pin', kwargs={'card_id': unassigned_card.id}),
            {'reason': 'Damaged warehouse insert during packaging', 'confirm_regen': 'yes'}
        )
        self.assertEqual(resp_regen.status_code, 302)
        unassigned_card.refresh_from_db()

        # Regeneration rejected on already active card
        resp_regen_active = manager_client.post(
            reverse('console:card_regenerate_pin', kwargs={'card_id': card.id}),
            {'reason': 'Try regenerating active card', 'confirm_regen': 'yes'}
        )
        # Should redirect back to card detail without regenerating
        card.refresh_from_db()
        self.assertEqual(card.status, Card.STATUS_ACTIVE)

    def test_generate_packaging_slips_pdf_service(self):
        """Verifies high-quality print-ready A4 PDF generation for packaging slips."""
        from apps.cards.services.packaging_service import generate_packaging_slips_pdf

        # Manifest with 9 cards (spans 2 pages: 8 slips on page 1, 1 slip on page 2)
        mock_manifest = {
            "batch_reference": "TEST-BATCH-PDF",
            "staff_email": "staff@strideid.com",
            "cards": [
                {
                    "card_id": i,
                    "card_code": f"ST-{i:08d}",
                    "pin": "123456",
                    "material": "Matte Black",
                    "created_at": "2026-11-21 10:00 UTC",
                }
                for i in range(1, 10)
            ],
        }

        pdf_buf = generate_packaging_slips_pdf(mock_manifest)
        self.assertIsNotNone(pdf_buf)
        pdf_bytes = pdf_buf.getvalue()
        self.assertTrue(len(pdf_bytes) > 1000)
        # Standard PDF magic header
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_regenerate_batch_activation_pins_service(self):
        """
        Verifies bulk PIN regeneration:
        - Re-keys hashes atomically
        - Creates replacement cache manifest
        - Audits with zero plaintext secrets
        - Fails closed on batches with active cards
        """
        from apps.cards.services.packaging_service import regenerate_batch_activation_pins
        from apps.core.models import AdminAuditLog
        from django.core.cache import cache

        cards, token = create_card_batch(
            count=3,
            material="metallic_silver",
            batch_reference="BATCH-REGEN-001",
            staff_user=self.staff_user,
        )
        old_hashes = [c.activation_code_hash for c in cards]

        updated_cards, new_token = regenerate_batch_activation_pins(
            batch_reference="BATCH-REGEN-001",
            staff_user=self.manager_user,
            reason="Physical packaging slips lost by courier",
            ip_address="127.0.0.1",
        )

        self.assertEqual(len(updated_cards), 3)
        self.assertNotEqual(token, new_token)

        # Confirm all hashes changed
        for idx, c in enumerate(updated_cards):
            c.refresh_from_db()
            self.assertNotEqual(c.activation_code_hash, old_hashes[idx])

        # Confirm replacement manifest exists in cache
        replacement_manifest = cache.get(f"packaging_manifest:{new_token}")
        self.assertIsNotNone(replacement_manifest)
        self.assertEqual(len(replacement_manifest["cards"]), 3)

        # Confirm audit log created with zero plaintext PINs
        audit = AdminAuditLog.objects.filter(
            action=AdminAuditLog.ACTION_PIN_REGENERATED,
            target_id="BATCH-REGEN-001",
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("lost by courier", audit.details.lower())

        # Now test failure when batch contains an ACTIVE card
        active_card = cards[0]
        active_card.status = Card.STATUS_ACTIVE
        active_card.save(update_fields=["status"])

        with self.assertRaises(ValueError) as ctx:
            regenerate_batch_activation_pins(
                batch_reference="BATCH-REGEN-001",
                staff_user=self.manager_user,
                reason="Attempt re-key with active card",
            )
        self.assertIn("Active card", str(ctx.exception))

    def test_card_model_pairing_status_and_urls(self):
        """Verifies operational pairing classifications and canonical/staging URLs."""
        card = Card.objects.create(
            card_code="ST-PAIRTEST",
            status=Card.STATUS_UNASSIGNED,
            is_warehouse_stock=True,
        )
        self.assertEqual(card.pairing_status, 'UNPAIRED')
        self.assertEqual(card.pairing_status_display, 'Unpaired Stock')

        card.status = Card.STATUS_RESERVED
        card.user = self.customer
        card.save()
        self.assertEqual(card.pairing_status, 'PAIRED_PENDING')
        self.assertEqual(card.pairing_status_display, 'Paired — Not Activated')

        card.status = Card.STATUS_ACTIVE
        card.save()
        self.assertEqual(card.pairing_status, 'ACTIVE')
        self.assertEqual(card.pairing_status_display, 'Active & Linked')

        self.assertEqual(card.get_canonical_production_url(), "https://strideid.com/c/ST-PAIRTEST/")
        self.assertEqual(card.get_staging_test_url(), "https://nfc-staging.up.railway.app/c/ST-PAIRTEST/")
