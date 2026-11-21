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
