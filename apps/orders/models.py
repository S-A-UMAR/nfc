from django.db import models
from django.conf import settings
import random
import string
from apps.cards.models import Card

class ProductPackage(models.Model):
    TYPE_CARD = 'card_only'
    TYPE_PERSONAL = 'personal_website'
    TYPE_BUSINESS = 'business_website'
    TYPE_CORPORATE = 'corporate'

    TYPE_CHOICES = (
        (TYPE_CARD, 'Smart NFC Card'),
        (TYPE_PERSONAL, 'Personal Identity (Card + Website)'),
        (TYPE_BUSINESS, 'Business Suite (Card + Business Website)'),
        (TYPE_CORPORATE, 'Corporate / Team Fleet'),
    )

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    package_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_CARD)
    price_ngn = models.PositiveIntegerField(help_text="Price in Nigerian Naira (NGN)")
    description = models.TextField()
    features = models.TextField(help_text="Features separated by newlines")
    badge = models.CharField(max_length=50, blank=True, help_text="e.g. Most Popular, Best Value")
    is_active = models.BooleanField(default=True)
    order_index = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order_index', 'price_ngn']

    def __str__(self):
        return f"{self.name} (₦{self.price_ngn:,.0f})"

    @property
    def feature_list(self):
        return [f.strip() for f in self.features.split('\n') if f.strip()]


class Order(models.Model):
    PAYMENT_PENDING = 'pending'
    PAYMENT_PAID = 'paid'
    PAYMENT_FAILED = 'failed'
    PAYMENT_REFUNDED = 'refunded'
    PAYMENT_CANCELLED = 'cancelled'

    PAYMENT_STATUS_CHOICES = (
        (PAYMENT_PENDING, 'Payment Pending'),
        (PAYMENT_PAID, 'Payment Confirmed'),
        (PAYMENT_FAILED, 'Payment Failed'),
        (PAYMENT_REFUNDED, 'Refunded'),
        (PAYMENT_CANCELLED, 'Cancelled'),
    )

    STATUS_RECEIVED = 'received'
    STATUS_PAID = 'payment_confirmed'
    STATUS_INFO_REQUIRED = 'info_required'
    STATUS_INFO_SUBMITTED = 'info_submitted'
    STATUS_DESIGNING = 'designing'
    STATUS_REVIEW = 'review'
    STATUS_PRODUCTION = 'production'
    STATUS_DELIVERY = 'delivery'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    ORDER_STATUS_CHOICES = (
        (STATUS_RECEIVED, 'Order Received'),
        (STATUS_PAID, 'Payment Confirmed'),
        (STATUS_INFO_REQUIRED, 'Information Required'),
        (STATUS_INFO_SUBMITTED, 'Information Submitted'),
        (STATUS_DESIGNING, 'Designing & Customizing'),
        (STATUS_REVIEW, 'Client Review'),
        (STATUS_PRODUCTION, 'Card Production / Encoding'),
        (STATUS_DELIVERY, 'Out for Delivery'),
        (STATUS_COMPLETED, 'Completed & Active'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    TIMELINE_STEPS = [
        ('received', 'Order Received'),
        ('payment_confirmed', 'Payment Confirmed'),
        ('info_submitted', 'Information Submitted'),
        ('designing', 'Designing'),
        ('review', 'Review'),
        ('production', 'Production'),
        ('delivery', 'Delivery'),
        ('completed', 'Completed'),
    ]

    order_number = models.CharField(max_length=40, unique=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
    package = models.ForeignKey(ProductPackage, on_delete=models.PROTECT, related_name='orders')
    amount = models.PositiveIntegerField(help_text="Final price paid in NGN")
    
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING, db_index=True)
    order_status = models.CharField(max_length=30, choices=ORDER_STATUS_CHOICES, default=STATUS_RECEIVED, db_index=True)
    
    card_assigned = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_assignments')
    
    shipping_name = models.CharField(max_length=150, blank=True)
    shipping_phone = models.CharField(max_length=50, blank=True)
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    
    customer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.order_number} - {self.package.name} ({self.user.display_name})"

    def save(self, *args, **kwargs):
        if not self.order_number:
            rand_suffix = ''.join(random.choices(string.digits, k=4))
            self.order_number = f"ORD-{random.randint(1000, 9999)}"
            while Order.objects.filter(order_number=self.order_number).exists():
                self.order_number = f"ORD-{random.randint(10000, 99999)}"
        super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.payment_status == self.PAYMENT_PAID

    @property
    def has_submitted_requirements(self):
        return hasattr(self, 'requirement') and self.requirement is not None


class OrderRequirement(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='requirement')
    full_name = models.CharField(max_length=150)
    title = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    
    business_name = models.CharField(max_length=150, blank=True)
    business_category = models.CharField(max_length=100, blank=True)
    business_description = models.TextField(blank=True)
    
    phone = models.CharField(max_length=50, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    
    social_instagram = models.CharField(max_length=200, blank=True)
    social_linkedin = models.CharField(max_length=200, blank=True)
    social_x = models.CharField(max_length=200, blank=True)
    social_tiktok = models.CharField(max_length=200, blank=True)
    social_facebook = models.CharField(max_length=200, blank=True)
    website_url = models.CharField(max_length=200, blank=True)
    
    website_type = models.CharField(max_length=50, default='none')
    pages_needed = models.CharField(max_length=300, blank=True, help_text="Comma separated pages (Home, About, Services, Gallery, Contact, etc.)")
    design_notes = models.TextField(blank=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Requirements for Order #{self.order.order_number}"
