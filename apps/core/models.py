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
