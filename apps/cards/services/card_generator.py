import secrets
import string
import re
from datetime import datetime
from django.db import transaction
from django.core.cache import cache
from django.utils import timezone
from apps.cards.models import Card
from apps.core.models import AdminAuditLog

# Approved STRIDE readable alphabet (32 characters, excludes 0, O, 1, I, L)
STRIDE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
STRIDE_CODE_REGEX = re.compile(r"^ST-[23456789ABCDEFGHJKMNPQRSTVWXYZ]{8}$")


def generate_single_card_code(max_retries: int = 20) -> str:
    """
    Generates a cryptographically random, canonical STRIDE card ID.
    Format: ST-XXXXXXXX (8 characters from STRIDE_ALPHABET)
    Example: ST-7K9M2P4R
    Enforces uniqueness with bounded retry logic.
    """
    for _ in range(max_retries):
        random_suffix = "".join(secrets.choice(STRIDE_ALPHABET) for _ in range(8))
        candidate = f"ST-{random_suffix}"
        if not Card.objects.filter(card_code=candidate).exists():
            return candidate
    raise RuntimeError("Failed to generate a unique card code after maximum retries.")


def generate_batch_reference() -> str:
    """Generates an operational batch identifier, e.g. BATCH-20261121-7K9M"""
    date_str = timezone.now().strftime("%Y%m%d")
    random_part = "".join(secrets.choice(STRIDE_ALPHABET) for _ in range(4))
    return f"BATCH-{date_str}-{random_part}"


def sanitize_csv_cell(value) -> str:
    """
    Prevents CSV Formula Injection (CWE-1236).
    If a cell starts with =, +, -, @, or tab/CR, prepend an apostrophe.
    """
    s = str(value) if value is not None else ""
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


def create_card_batch(
    count: int,
    material: str = "matte_black",
    batch_reference: str = None,
    staff_user=None,
    ip_address: str = None,
):
    """
    Transaction-safe generation of a batch of cards (1, 5, 10, 25, 50, 100).
    Every card is initialized with:
    - status = UNASSIGNED
    - is_warehouse_stock = True
    - provisioning_stage = generated
    - batch_reference = batch_reference
    - Cryptographically random card_code (ST-XXXXXXXX)
    - Cryptographically random 8-char PIN (SHA-256 hashed into DB)

    Returns:
        (created_cards, packaging_token)
        packaging_token is a temporary 10-minute cache key containing the plaintext PINs
        for the one-time packaging slip and CSV export.
    """
    if count < 1 or count > 100:
        raise ValueError("Batch count must be between 1 and 100.")

    valid_materials = dict(Card.MATERIAL_CHOICES)
    if material not in valid_materials:
        material = "matte_black"

    if not batch_reference:
        batch_reference = generate_batch_reference()

    created_cards = []
    manifest_records = []

    with transaction.atomic():
        for _ in range(count):
            card_code = generate_single_card_code()
            card = Card(
                card_code=card_code,
                material=material,
                status=Card.STATUS_UNASSIGNED,
                is_warehouse_stock=True,
                batch_reference=batch_reference,
                provisioning_stage=Card.STAGE_GENERATED,
            )
            # Generates plaintext PIN, hashes into activation_code_hash
            plain_pin = card.generate_activation_code()
            card.save()

            created_cards.append(card)
            manifest_records.append({
                "card_id": card.id,
                "card_code": card.card_code,
                "pin": plain_pin,
                "plaintext_pin": plain_pin,
                "material": card.get_material_display(),
                "batch_reference": batch_reference,
                "created_at": card.created_at.strftime("%Y-%m-%d %H:%M UTC"),
                "nfc_url": card.get_full_nfc_url(),
            })

        # Immutable Audit Log — NEVER logs the plaintext PINs
        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_BULK_CREATED,
            staff_user=staff_user,
            target_repr=f"Batch {batch_reference} ({len(created_cards)} cards)",
            target_model="Card",
            target_id=batch_reference,
            previous_state="",
            new_state=Card.STATUS_UNASSIGNED,
            details=f"Generated {len(created_cards)} cards in batch {batch_reference} with finish {material}. Warehouse locked.",
            ip_address=ip_address,
        )

    # Store ephemeral one-time packaging manifest in cache (15-minute TTL)
    token = secrets.token_urlsafe(32)
    cache.set(
        f"packaging_manifest:{token}",
        {
            "batch_reference": batch_reference,
            "created_at": timezone.now().strftime("%Y-%m-%d %H:%M UTC"),
            "staff_email": getattr(staff_user, "email", "system"),
            "cards": manifest_records,
        },
        timeout=900,  # 15 minutes
    )
    if batch_reference:
        cache.set(f"batch_active_packaging_token:{batch_reference}", token, timeout=900)

    return created_cards, token
