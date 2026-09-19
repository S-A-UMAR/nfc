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
        help_text="Unique internal ID written to NFC, e.g. BR-000001"
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
    notes = models.TextField(blank=True)
    activation_code_hash = models.CharField(
        max_length=128, 
        blank=True, 
        null=True, 
        help_text="SHA-256 hashed secret PIN/code printed on physical packaging"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['card_code']

    def set_activation_code(self, code: str):
        """Hashes and sets the physical card secret activation code."""
        import hashlib
        self.activation_code_hash = hashlib.sha256(code.strip().upper().encode('utf-8')).hexdigest()

    def check_activation_code(self, code: str) -> bool:
        """Constant-time verification of physical card activation code."""
        import hashlib
        import hmac
        if not self.activation_code_hash:
            return True  # If legacy card has no hash set, fall back to open activation or code not required
        actual = hashlib.sha256(code.strip().upper().encode('utf-8')).hexdigest()
        return hmac.compare_digest(self.activation_code_hash, actual)

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
        return f"https://uzyra.com{self.nfc_url_path}"

    def generate_qr_code(self, base_url="https://uzyra.com"):
        """Generate high-contrast minimal graphite QR code."""
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
