import os
import io
import qrcode
from django.db import models
from django.conf import settings
from django.core.files.base import ContentFile
from apps.profiles.models import Profile

class Card(models.Model):
    STATUS_UNASSIGNED = 'UNASSIGNED'
    STATUS_RESERVED = 'RESERVED'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_SUSPENDED = 'SUSPENDED'
    STATUS_LOST = 'LOST'
    STATUS_REPLACED = 'REPLACED'

    STATUS_CHOICES = (
        (STATUS_UNASSIGNED, 'Unassigned (In Stock)'),
        (STATUS_RESERVED, 'Reserved (Ordered)'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_LOST, 'Reported Lost'),
        (STATUS_REPLACED, 'Replaced'),
    )

    MATERIAL_CHOICES = (
        ('matte_black', 'Matte Graphite Black'),
        ('metallic_silver', 'Brushed Silver'),
        ('carbon_dark', 'Carbon Fiber Minimal'),
    )

    card_code = models.CharField(
        max_length=50, 
        unique=True, 
        db_index=True, 
        help_text="Unique internal ID written to NFC, e.g. ST-000001"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='cards'
    )
    profile = models.ForeignKey(
        Profile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='cards'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default=STATUS_UNASSIGNED,
        db_index=True
    )
    material = models.CharField(
        max_length=30, 
        choices=MATERIAL_CHOICES, 
        default='matte_black'
    )
    qr_code_image = models.ImageField(
        upload_to='cards/qrcodes/', 
        blank=True, 
        null=True
    )
    replacement_for = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='replacements'
    )
    STAGE_GENERATED = 'generated'
    STAGE_ENCODED = 'encoded'
    STAGE_PACKAGED = 'packaged'
    STAGE_READY = 'ready'

    PROVISIONING_STAGE_CHOICES = (
        (STAGE_GENERATED, 'Record Generated'),
        (STAGE_ENCODED, 'NFC Written & QR Printed'),
        (STAGE_PACKAGED, 'Sleeve Sealed with PIN'),
        (STAGE_READY, 'Ready for Dispatch / Storage'),
    )

    notes = models.TextField(blank=True)
    activation_code_hash = models.CharField(
        max_length=128, 
        blank=True, 
        null=True, 
        help_text="SHA-256 hashed secret PIN/code printed on physical packaging"
    )
    is_warehouse_stock = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Designates unallocated warehouse inventory that cannot be claimed until assigned/dispatched."
    )
    batch_reference = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Manufacturing batch identifier, e.g. BATCH-20261121-7K9M"
    )
    provisioning_stage = models.CharField(
        max_length=30,
        choices=PROVISIONING_STAGE_CHOICES,
        default=STAGE_GENERATED,
        db_index=True,
        help_text="Manufacturing and provisioning readiness stage"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['card_code']

    def set_activation_code(self, code: str):
        """Hashes and sets the physical card secret activation code.
        Hyphens are stripped before hashing so set('XXXX-XXXX') and set('XXXXXXXX') produce
        the same stored hash, keeping set/check symmetric.
        """
        import hashlib
        self.activation_code_hash = hashlib.sha256(code.strip().upper().replace('-', '').encode('utf-8')).hexdigest()

    def check_activation_code(self, code: str) -> bool:
        """Constant-time verification of physical card activation code.
        Accepts both hyphenated (XXXX-XXXX) and unhyphenated (XXXXXXXX) formats.
        Supports:
        1. Ungrouped / normalized format (XXXXXXXX)
        2. Historical grouped format with hyphen (XXXX-XXXX)
        3. Raw entered format
        Performs constant-time comparison across candidate hashes to prevent timing side channels.
        """
        import hashlib
        import hmac
        if not self.activation_code_hash or not code or not isinstance(code, str):
            return False
        raw = code.strip().upper()
        if not raw:
            return False
        cleaned = raw.replace('-', '')
        if not cleaned:
            return False

        # Candidate 1: Normalized without hyphen
        cand1 = hashlib.sha256(cleaned.encode('utf-8')).hexdigest()
        match1 = hmac.compare_digest(self.activation_code_hash, cand1)

        # Candidate 2: Raw as entered (handles historical hash if entered with hyphen)
        cand2 = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        match2 = hmac.compare_digest(self.activation_code_hash, cand2)

        # Candidate 3: Standard 4-4 hyphenated format if cleaned length is 8 (handles historical hash if customer entered without hyphen)
        match3 = False
        if len(cleaned) == 8:
            hyphenated = f"{cleaned[:4]}-{cleaned[4:]}"
            cand3 = hashlib.sha256(hyphenated.encode('utf-8')).hexdigest()
            match3 = hmac.compare_digest(self.activation_code_hash, cand3)

        return match1 or match2 or match3

    def generate_activation_code(self) -> str:
        """Generates a secure 8-character activation PIN, sets the hash, and returns the plaintext PIN."""
        import secrets
        import string
        chars = string.ascii_uppercase.replace('O', '').replace('I', '') + '23456789'
        part1 = "".join(secrets.choice(chars) for _ in range(4))
        part2 = "".join(secrets.choice(chars) for _ in range(4))
        plain_code = f"{part1}-{part2}"
        self.set_activation_code(plain_code)
        return plain_code

    def __str__(self):
        owner = self.user.display_name if self.user else "Unassigned"
        return f"{self.card_code} [{self.get_status_display()}] - {owner}"

    @property
    def nfc_url_path(self):
        """Standard relative redirect URL stored on the physical NFC chip."""
        return f"/c/{self.card_code}/"

    def get_full_nfc_url(self, request=None):
        """Absolute NFC URL."""
        if request:
            return request.build_absolute_uri(self.nfc_url_path)
        base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        return f"{base_url.rstrip('/')}{self.nfc_url_path}"

    def generate_qr_code(self, base_url=None):
        """Generate high-contrast minimal graphite QR code."""
        if not base_url:
            base_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        target_url = f"{base_url.rstrip('/')}/c/{self.card_code}/"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0A0A0A", back_color="#FFFFFF")
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        filename = f"qr_{self.card_code}.png"
        self.qr_code_image.save(filename, ContentFile(buffer.getvalue()), save=False)

    def save(self, *args, **kwargs):
        if not self.qr_code_image:
            self.generate_qr_code()
        super().save(*args, **kwargs)

    @property
    def pairing_status(self) -> str:
        """
        Operational pairing classification for STRIDE Console:
        - 'ACTIVE': Fully activated by customer.
        - 'PAIRED_PENDING': Reserved/assigned to customer/order, awaiting customer PIN activation.
        - 'UNPAIRED': Unassigned inventory stock in warehouse.
        - Other states: 'SUSPENDED', 'LOST', 'REPLACED'.
        """
        if self.status == self.STATUS_ACTIVE:
            return 'ACTIVE'
        if self.status in (self.STATUS_SUSPENDED, self.STATUS_LOST, self.STATUS_REPLACED):
            return self.status
        if self.user or self.status == self.STATUS_RESERVED:
            return 'PAIRED_PENDING'
        return 'UNPAIRED'

    @property
    def pairing_status_display(self) -> str:
        labels = {
            'UNPAIRED': 'Unpaired Stock',
            'PAIRED_PENDING': 'Paired — Not Activated',
            'ACTIVE': 'Active & Linked',
            'SUSPENDED': 'Suspended',
            'LOST': 'Reported Lost',
            'REPLACED': 'Replaced',
        }
        return labels.get(self.pairing_status, self.get_status_display())

    @property
    def pairing_status_badge(self) -> str:
        classes = {
            'UNPAIRED': 'ops-badge-unpaired',
            'PAIRED_PENDING': 'ops-badge-paired',
            'ACTIVE': 'ops-badge-active',
            'SUSPENDED': 'ops-badge-suspended',
            'LOST': 'ops-badge-lost',
            'REPLACED': 'ops-badge-replaced',
        }
        return classes.get(self.pairing_status, 'ops-badge-unpaired')

    def get_canonical_production_url(self) -> str:
        """Hardware canonical URL written to physical chip / laser QR."""
        return f"https://strideid.com/c/{self.card_code}/"

    def get_staging_test_url(self) -> str:
        """Staging environment testing route."""
        return f"https://nfc-staging.up.railway.app/c/{self.card_code}/"


class CardEvent(models.Model):
    EVENT_NFC = 'nfc_tap'
    EVENT_QR = 'qr_scan'
    EVENT_DIRECT = 'direct_view'

    EVENT_CHOICES = (
        (EVENT_NFC, 'NFC Physical Tap'),
        (EVENT_QR, 'QR Code Scan'),
        (EVENT_DIRECT, 'Direct Web Visit'),
    )

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, default=EVENT_NFC)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.card.card_code} - {self.get_event_type_display()} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
