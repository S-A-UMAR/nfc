from django.db import models
from apps.orders.models import Order

class Payment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Successful'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.PositiveIntegerField(help_text="Amount in NGN")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    provider = models.CharField(max_length=50, default='paystack')
    
    paystack_access_code = models.CharField(max_length=100, blank=True)
    channel = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=10, default='NGN')
    gateway_response = models.CharField(max_length=255, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference} - ₦{self.amount:,.0f} [{self.get_status_display()}]"
