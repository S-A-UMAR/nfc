import csv
import io
import secrets
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from apps.cards.models import Card
from apps.core.models import AdminAuditLog
from apps.cards.services.card_generator import sanitize_csv_cell


def get_packaging_manifest(token: str):
    """Retrieves the ephemeral packaging manifest from cache by token."""
    if not token or not isinstance(token, str):
        return None
    return cache.get(f"packaging_manifest:{token}")


def acknowledge_packaging_manifest(token: str) -> bool:
    """Explicitly deletes the ephemeral packaging manifest from cache."""
    if not token:
        return False
    return bool(cache.delete(f"packaging_manifest:{token}"))


def build_packaging_csv_content(manifest_data: dict) -> str:
    """
    Builds the restricted packaging CSV containing Card ID and Activation PIN.
    Applies formula injection protection.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Batch_Reference",
        "Card_Code",
        "Activation_PIN",
        "Material_Finish",
        "NFC_Target_URL",
        "Generated_At",
    ])

    batch_ref = manifest_data.get("batch_reference", "")
    for item in manifest_data.get("cards", []):
        writer.writerow([
            sanitize_csv_cell(item.get("batch_reference", batch_ref)),
            sanitize_csv_cell(item.get("card_code", "")),
            sanitize_csv_cell(item.get("pin", "")),
            sanitize_csv_cell(item.get("material", "")),
            sanitize_csv_cell(item.get("nfc_url", "")),
            sanitize_csv_cell(item.get("created_at", "")),
        ])

    return output.getvalue()


def generate_packaging_slips_pdf(manifest_data: dict) -> io.BytesIO:
    """
    Generates a high-quality, print-ready A4 PDF containing all packaging slips in the batch.
    Layout:
    - Standard A4 sheet (595.28 x 841.89 pt)
    - 2 columns x 4 rows = 8 slips per page
    - Dotted / dashed cut-lines for clean trimming
    - Monospace high-visibility Card ID and Activation PIN
    - Minimal, economic black & white toner usage for office printers
    - Multiple pages automatically partitioned with page numbering
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    cards = manifest_data.get("cards", [])
    batch_ref = manifest_data.get("batch_reference", "BATCH")
    
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    page_w, page_h = A4
    margin_x = 28.0
    margin_y = 30.0
    cols = 2
    rows = 4
    col_gap = 12.0
    row_gap = 12.0
    slips_per_page = cols * rows

    card_w = (page_w - (2 * margin_x) - ((cols - 1) * col_gap)) / cols
    card_h = (page_h - (2 * margin_y) - ((rows - 1) * row_gap)) / rows

    total_cards = len(cards)
    total_pages = max(1, (total_cards + slips_per_page - 1) // slips_per_page)

    for idx, card in enumerate(cards):
        slip_index_on_page = idx % slips_per_page
        current_page = (idx // slips_per_page) + 1

        col = slip_index_on_page % cols
        row = slip_index_on_page // cols  # 0 to 3, top to bottom

        x = margin_x + col * (card_w + col_gap)
        # In PDF coordinates, (0, 0) is bottom-left, so row 0 is top
        y = page_h - margin_y - (row + 1) * card_h - (row * row_gap)

        # 1. Outer dashed cut line
        c.saveState()
        c.setDash(2.5, 3.0)
        c.setStrokeColorRGB(0.68, 0.68, 0.72)
        c.setLineWidth(0.75)
        c.roundRect(x, y, card_w, card_h, radius=4, stroke=1, fill=0)
        c.restoreState()

        # 2. Header: STRIDE Brand & Badge
        c.saveState()
        c.setFont("Helvetica-Bold", 10.5)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(x + 12, y + card_h - 22, "STRIDE")

        c.setFont("Helvetica-Bold", 6.0)
        c.setFillColorRGB(0.45, 0.45, 0.50)
        c.drawRightString(x + card_w - 12, y + card_h - 20, "PACKAGING SLIP")

        # Divider line
        c.setStrokeColorRGB(0.88, 0.88, 0.90)
        c.setLineWidth(0.5)
        c.line(x + 12, y + card_h - 28, x + card_w - 12, y + card_h - 28)
        c.restoreState()

        # 3. Card ID Section
        c.saveState()
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColorRGB(0.40, 0.40, 0.45)
        c.drawString(x + 12, y + card_h - 42, "CARD ID / HARDWARE CODE")

        c.setFont("Courier-Bold", 12.5)
        c.setFillColorRGB(0.08, 0.08, 0.10)
        card_code = str(card.get("card_code", "ST-00000000"))
        c.drawString(x + 12, y + card_h - 58, card_code)
        c.restoreState()

        # 4. Activation PIN Box (High-Contrast, Clear Reveal)
        c.saveState()
        pin_box_y = y + 42
        pin_box_h = 38
        pin_box_w = card_w - 24

        # Background fill
        c.setFillColorRGB(0.96, 0.96, 0.97)
        c.setStrokeColorRGB(0.80, 0.80, 0.85)
        c.setLineWidth(0.75)
        c.roundRect(x + 12, pin_box_y, pin_box_w, pin_box_h, radius=4, stroke=1, fill=1)

        c.setFont("Helvetica-Bold", 6.0)
        c.setFillColorRGB(0.35, 0.35, 0.40)
        c.drawString(x + 18, pin_box_y + pin_box_h - 10, "ACTIVATION PIN (CONFIDENTIAL)")

        # Monospace Formatted PIN
        pin_str = str(card.get("pin") or card.get("plaintext_pin", "----"))
        c.setFont("Courier-Bold", 14.0)
        c.setFillColorRGB(0.05, 0.05, 0.05)
        c.drawCentredString(x + 12 + pin_box_w / 2.0, pin_box_y + 10, pin_str)
        c.restoreState()

        # 5. Metadata Line
        c.saveState()
        material = card.get("material", "Standard")
        meta_str = f"Finish: {material}   ·   Batch: {batch_ref}"
        c.setFont("Helvetica", 6.5)
        c.setFillColorRGB(0.45, 0.45, 0.50)
        c.drawString(x + 12, y + 27, meta_str[:42])
        c.restoreState()

        # 6. Privacy & Activation Instruction
        c.saveState()
        c.setFont("Helvetica-Oblique", 5.5)
        c.setFillColorRGB(0.50, 0.50, 0.55)
        c.drawString(x + 12, y + 14, "Do not share this PIN. Activate your physical card at strideid.com/activate")
        c.restoreState()

        # If last slip on current page or last slip overall, show page & footer
        if slip_index_on_page == slips_per_page - 1 or idx == total_cards - 1:
            c.saveState()
            c.setFont("Helvetica", 7.0)
            c.setFillColorRGB(0.55, 0.55, 0.60)
            c.drawCentredString(
                page_w / 2.0, 
                15, 
                f"STRIDE NFC Hardware Operations   ·   Batch {batch_ref}   ·   Page {current_page} of {total_pages}"
            )
            c.restoreState()
            c.showPage()

    c.save()
    buf.seek(0)
    return buf


def regenerate_card_activation_pin(
    card_id: int,
    staff_user,
    reason: str,
    ip_address: str = None,
):
    """
    Emergency PIN regeneration workflow for unactivated cards.
    Requires:
    - Card must not be active, suspended, or replaced
    - Valid reason string
    - Atomic transaction with row locking
    - Replaces activation_code_hash atomically
    - Logs to AdminAuditLog without leaking the plaintext PIN
    - Returns (card, new_plain_pin, one_time_token)
    """
    if not reason or len(reason.strip()) < 5:
        raise ValueError("A clear operational reason (at least 5 characters) is required for PIN regeneration.")

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)

        if card.status == Card.STATUS_ACTIVE:
            raise ValueError(f"Card '{card.card_code}' is already active and in customer possession. Active cards cannot have PINs regenerated.")

        if card.status in (Card.STATUS_LOST, Card.STATUS_REPLACED):
            raise ValueError(f"Card '{card.card_code}' is marked {card.get_status_display()} and cannot have its PIN regenerated.")

        # Generate new plaintext PIN and update hash
        new_plain_pin = card.generate_activation_code()
        # Ensure card is warehouse stock if not yet assigned to an order
        if not card.user and card.status == Card.STATUS_UNASSIGNED:
            card.is_warehouse_stock = True
        card.save(update_fields=["activation_code_hash", "is_warehouse_stock"])

        # Audit log entry — strictly does NOT log the plaintext PIN
        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_PIN_REGENERATED,
            staff_user=staff_user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state="Previous PIN Hash Invalidated",
            new_state="New Cryptographic PIN Hash Set",
            details=f"Emergency PIN regeneration. Reason: {reason.strip()}",
            ip_address=ip_address,
        )

    # Store in single-card packaging cache token (15-min TTL)
    token = secrets.token_urlsafe(32)
    single_manifest = {
        "batch_reference": card.batch_reference or "SINGLE-REGEN",
        "created_at": timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
        "staff_email": getattr(staff_user, "email", "system"),
        "cards": [{
            "card_id": card.id,
            "card_code": card.card_code,
            "pin": new_plain_pin,
            "plaintext_pin": new_plain_pin,
            "material": card.get_material_display(),
            "batch_reference": card.batch_reference or "SINGLE-REGEN",
            "created_at": timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
            "nfc_url": card.get_full_nfc_url(),
        }],
    }
    cache.set(f"packaging_manifest:{token}", single_manifest, timeout=900)

    return card, new_plain_pin, token


def regenerate_batch_activation_pins(
    batch_reference: str,
    staff_user,
    reason: str,
    ip_address: str = None,
):
    """
    Emergency Bulk PIN regeneration for an entire unactivated production batch.
    Manager-only recovery workflow.
    Requirements:
    - Atomically locks and updates all cards in the batch.
    - Fails closed: if ANY card is ACTIVE, LOST, REPLACED, or SUSPENDED, the entire batch
      operation is aborted and zero PINs are changed.
    - Generates new plaintext PINs in memory, sets activation_code_hash.
    - Emits immutable AdminAuditLog with reason and count (zero plaintext secrets).
    - Stores replacement credentials in ephemeral 15-minute cache packaging manifest.
    - Returns (updated_cards, packaging_token).
    """
    if not batch_reference or not str(batch_reference).strip():
        raise ValueError("A valid batch reference is required.")

    clean_batch = str(batch_reference).strip()

    if not reason or len(reason.strip()) < 5:
        raise ValueError("A clear operational reason (at least 5 characters) is required for bulk PIN regeneration.")

    manifest_records = []
    updated_cards = []

    with transaction.atomic():
        cards = list(Card.objects.select_for_update().filter(batch_reference=clean_batch).order_by('card_code'))
        if not cards:
            raise ValueError(f"No cards found matching batch reference '{clean_batch}'.")

        # Invariant: Reject if any card in the batch has already been activated or decommissioned
        for card in cards:
            if card.status == Card.STATUS_ACTIVE:
                raise ValueError(
                    f"Batch '{clean_batch}' contains active card '{card.card_code}' in customer hands. "
                    "Active cards cannot have PINs regenerated. Operation aborted."
                )
            if card.status in (Card.STATUS_LOST, Card.STATUS_REPLACED, Card.STATUS_SUSPENDED):
                raise ValueError(
                    f"Batch '{clean_batch}' contains card '{card.card_code}' in '{card.get_status_display()}' state. "
                    "Cannot regenerate PINs for decommissioned cards. Operation aborted."
                )

        # All cards are eligible unactivated stock: atomically re-key
        for card in cards:
            new_plain_pin = card.generate_activation_code()
            if not card.user and card.status == Card.STATUS_UNASSIGNED:
                card.is_warehouse_stock = True
            card.save(update_fields=["activation_code_hash", "is_warehouse_stock"])

            updated_cards.append(card)
            manifest_records.append({
                "card_id": card.id,
                "card_code": card.card_code,
                "pin": new_plain_pin,
                "plaintext_pin": new_plain_pin,
                "material": card.get_material_display(),
                "batch_reference": clean_batch,
                "created_at": card.created_at.strftime("%Y-%m-%d %H:%M UTC") if card.created_at else "",
                "nfc_url": card.get_full_nfc_url(),
            })

        # Immutable Audit Record — NEVER logs plaintext PINs
        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_PIN_REGENERATED,
            staff_user=staff_user,
            target_repr=f"Batch {clean_batch} ({len(cards)} cards)",
            target_model="Card",
            target_id=clean_batch,
            previous_state="Batch PIN Hashes Invalidated",
            new_state="New Cryptographic PIN Hashes Set",
            details=f"Emergency bulk PIN regeneration for {len(cards)} cards in batch {clean_batch}. Reason: {reason.strip()}",
            ip_address=ip_address,
        )

    # Ephemeral replacement packaging manifest (15-min TTL)
    token = secrets.token_urlsafe(32)
    batch_manifest = {
        "batch_reference": clean_batch,
        "created_at": timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
        "staff_email": getattr(staff_user, "email", "system"),
        "cards": manifest_records,
    }
    cache.set(f"packaging_manifest:{token}", batch_manifest, timeout=900)

    return updated_cards, token
