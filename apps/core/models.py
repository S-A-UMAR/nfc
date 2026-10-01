from django.db import models

class ContactMessage(models.Model):
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} from {self.full_name} ({self.email})"


from django.conf import settings

class AdminAuditLog(models.Model):
    """
    Authoritative audit record of sensitive staff/administrative operations.
    Tracks card lifecycle, user/account changes, website actions, and order updates.
    """
    ACTION_CARD_CREATED = 'card_created'
    ACTION_CARD_BULK_CREATED = 'card_bulk_created'
    ACTION_CARD_ASSIGNED = 'card_assigned'
    ACTION_CARD_REASSIGNED = 'card_reassigned'
    ACTION_CARD_SUSPENDED = 'card_suspended'
    ACTION_CARD_RESTORED = 'card_restored'
    ACTION_CARD_MARKED_LOST = 'card_marked_lost'
    ACTION_CARD_REPLACED = 'card_replaced'
    ACTION_CUSTOMER_STATUS = 'customer_status_changed'
    ACTION_WEBSITE_STATUS = 'website_status_changed'
    ACTION_ORDER_STATUS = 'order_status_changed'

    ACTION_CHOICES = (
        (ACTION_CARD_CREATED, 'Card Created'),
        (ACTION_CARD_BULK_CREATED, 'Cards Bulk Created'),
        (ACTION_CARD_ASSIGNED, 'Card Assigned'),
        (ACTION_CARD_REASSIGNED, 'Card Reassigned'),
        (ACTION_CARD_SUSPENDED, 'Card Suspended'),
        (ACTION_CARD_RESTORED, 'Card Restored'),
        (ACTION_CARD_MARKED_LOST, 'Card Marked Lost'),
        (ACTION_CARD_REPLACED, 'Card Replaced'),
        (ACTION_CUSTOMER_STATUS, 'Customer Status Changed'),
        (ACTION_WEBSITE_STATUS, 'Website Status Changed'),
        (ACTION_ORDER_STATUS, 'Order Status Changed'),
    )

    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_audit_logs'
    )
    target_repr = models.CharField(max_length=200, help_text="e.g. Card UZY-CARD-000001 or Customer john@example.com")
    target_model = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    previous_state = models.CharField(max_length=255, blank=True)
    new_state = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['target_model', 'target_id']),
        ]

    def __str__(self):
        staff = self.staff_user.email if self.staff_user else "System"
        return f"[{self.get_action_display()}] {self.target_repr} by {staff} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def log(cls, action, staff_user, target_repr, target_model='', target_id='', previous_state='', new_state='', details='', ip_address=None):
        return cls.objects.create(
            action=action,
            staff_user=staff_user,
            target_repr=str(target_repr)[:200],
            target_model=str(target_model)[:50],
            target_id=str(target_id)[:50],
            previous_state=str(previous_state)[:255],
            new_state=str(new_state)[:255],
            details=details,
            ip_address=ip_address,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Business Inquiry Model — Phase 14
# ─────────────────────────────────────────────────────────────────────────────

class BusinessInquiry(models.Model):
    """
    Lightweight inquiry record for businesses and organisations requesting
    custom NFC / digital solutions from UZYRA.

    Intentionally lean — no automatic provisioning, quotations or contracts.
    Future: may be linked to a formal Business/Account entity once demand exists.
    """

    # ── Service Categories ──────────────────────────────────────────────────
    SERVICE_COMPANY_TEAM  = 'company_team'
    SERVICE_EVENT         = 'event'
    SERVICE_EVENT_CENTER  = 'event_center'
    SERVICE_SECURITY      = 'security'
    SERVICE_CUSTOM_CARD   = 'custom_card'
    SERVICE_CARD_WEBSITE  = 'card_website'
    SERVICE_OTHER         = 'other'

    SERVICE_CHOICES = (
        (SERVICE_COMPANY_TEAM,  'Company & Team NFC Cards'),
        (SERVICE_EVENT,         'Event NFC Solutions'),
        (SERVICE_EVENT_CENTER,  'Event Center Solutions'),
        (SERVICE_SECURITY,      'Security Personnel Cards'),
        (SERVICE_CUSTOM_CARD,   'Custom Branded NFC Cards'),
        (SERVICE_CARD_WEBSITE,  'NFC Card + Website'),
        (SERVICE_OTHER,         'Other Custom Solution'),
    )

    # ── Pipeline Statuses ───────────────────────────────────────────────────
    STATUS_NEW          = 'new'
    STATUS_CONTACTED    = 'contacted'
    STATUS_CONSULTATION = 'consultation'
    STATUS_PROPOSAL     = 'proposal'
    STATUS_WON          = 'won'
    STATUS_CLOSED       = 'closed'

    STATUS_CHOICES = (
        (STATUS_NEW,          'New'),
        (STATUS_CONTACTED,    'Contacted'),
        (STATUS_CONSULTATION, 'In Consultation'),
        (STATUS_PROPOSAL,     'Proposal Sent'),
        (STATUS_WON,          'Won'),
        (STATUS_CLOSED,       'Closed'),
    )

    # ── Inquiry Fields ──────────────────────────────────────────────────────
    full_name               = models.CharField(max_length=150)
    company_name            = models.CharField(max_length=200, blank=True)
    email                   = models.EmailField()
    phone                   = models.CharField(max_length=50, blank=True)
    service_type            = models.CharField(max_length=30, choices=SERVICE_CHOICES, default=SERVICE_OTHER)
    estimated_card_quantity = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. 50, 100–200, 500+"
    )
    needs_website           = models.BooleanField(default=False)
    message                 = models.TextField()

    # ── Pipeline / Staff Fields ─────────────────────────────────────────────
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    admin_notes    = models.TextField(blank=True, help_text="Internal staff notes — not visible to customer.")
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_staff': True},
        related_name='assigned_inquiries',
    )

    # ── Metadata ─────────────────────────────────────────────────────────────
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering         = ['-created_at']
        verbose_name     = 'Business Inquiry'
        verbose_name_plural = 'Business Inquiries'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        company = f" ({self.company_name})" if self.company_name else ""
        return f"[{self.get_status_display()}] {self.full_name}{company} — {self.get_service_type_display()}"

    @property
    def display_quantity(self):
        return self.estimated_card_quantity or 'Not specified'

    @property
    def status_badge_class(self):
        return {
            self.STATUS_NEW:          'badge-info',
            self.STATUS_CONTACTED:    'badge-warning',
            self.STATUS_CONSULTATION: 'badge-warning',
            self.STATUS_PROPOSAL:     'badge-silver',
            self.STATUS_WON:          'badge-success',
            self.STATUS_CLOSED:       'badge-danger',
        }.get(self.status, 'badge-silver')
