from django.db import models
from apps.profiles.models import Profile
from apps.cards.models import Card

class AnalyticsEvent(models.Model):
    TYPE_PROFILE_VIEW = 'profile_view'
    TYPE_CARD_TAP = 'card_tap'
    TYPE_QR_SCAN = 'qr_scan'
    TYPE_WHATSAPP = 'whatsapp_click'
    TYPE_CALL = 'call_click'
    TYPE_EMAIL = 'email_click'
    TYPE_WEBSITE = 'website_click'  # Profile external link click
    TYPE_SOCIAL = 'social_click'
    TYPE_VCARD = 'vcard_download'
    TYPE_WEBSITE_PAGE_VIEW = 'website_page_view'
    TYPE_WEBSITE_CTA_CLICK = 'website_cta_click'

    TYPE_CHOICES = (
        (TYPE_PROFILE_VIEW, 'Profile View'),
        (TYPE_CARD_TAP, 'NFC Card Tap'),
        (TYPE_QR_SCAN, 'QR Code Scan'),
        (TYPE_WHATSAPP, 'WhatsApp Click'),
        (TYPE_CALL, 'Phone Call Click'),
        (TYPE_EMAIL, 'Email Click'),
        (TYPE_WEBSITE, 'External Website Click'),
        (TYPE_SOCIAL, 'Social Media Link Click'),
        (TYPE_VCARD, 'Saved Contact (vCard)'),
        (TYPE_WEBSITE_PAGE_VIEW, 'Website View'),
        (TYPE_WEBSITE_CTA_CLICK, 'Website CTA Click'),
    )

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True, related_name='analytics_events')
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics_events')
    website = models.ForeignKey('websites.Website', on_delete=models.SET_NULL, null=True, blank=True, related_name='analytics_events')
    event_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    target_label = models.CharField(max_length=150, blank=True, help_text="e.g. Instagram, Portfolio Button, Call Now")
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    referer = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['profile', 'timestamp']),
            models.Index(fields=['website', 'timestamp']),
            models.Index(fields=['card', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
        ]

    def __str__(self):
        target = f" ({self.target_label})" if self.target_label else ""
        return f"{self.get_event_type_display()}{target} on {self.profile or 'Website'} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
