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

    @classmethod
    def ensure_default_packages(cls, force=False):
        """
        Ensures the 4 standard production packages exist and are active in the database.
        Safe to call on any environment to prevent empty packages or broken checkout redirects.
        """
        defaults = [
            {
                'code': 'smart-card',
                'name': 'Smart NFC Card',
                'package_type': cls.TYPE_CARD,
                'price_ngn': 25000,
                'description': 'Sleek matte-black physical NFC smart card paired with a lifetime digital profile. One-time purchase, zero monthly fees.',
                'features': (
                    'Matte Obsidian NFC Card with Silver Finish\n'
                    'Embedded NTAG216 High-Speed Microchip\n'
                    'High-Contrast Dynamic Laser QR Backup\n'
                    'Lifetime Verified Mobile Digital Profile\n'
                    '1-Tap Save Contact (.vcf) to Phonebook\n'
                    'Unlimited Real-time Profile Updates\n'
                    'Compatible with all iPhones & Androids (No App Required)\n'
                    'Zero Monthly or Annual Subscription Fees'
                ),
                'badge': 'Essential',
                'is_active': True,
                'order_index': 1,
            },
            {
                'code': 'personal-suite',
                'name': 'Personal Identity Suite',
                'package_type': cls.TYPE_PERSONAL,
                'price_ngn': 65000,
                'description': 'For executives, creators, and consultants wanting complete personal branding, direct link mode, and interactive networking.',
                'features': (
                    'Premium Matte Obsidian NFC Smart Card Included\n'
                    'Custom Laser-Engraved Full Name & Handle\n'
                    'Verified Digital Profile with Custom Username Link\n'
                    'Direct Link Mode (Instant Routing to WhatsApp/LinkedIn)\n'
                    '15+ Luxury Theme Styles & Custom Color Palettes\n'
                    'Bio, Services & Project Showcase Hub\n'
                    'Real-time Tap & Scan Interaction Analytics\n'
                    'Free Express Tracked Delivery Nationwide\n'
                    'Lifetime Access — Buy Once, Own Forever'
                ),
                'badge': 'Most Popular',
                'is_active': True,
                'order_index': 2,
            },
            {
                'code': 'business-suite',
                'name': 'Business Growth Suite',
                'package_type': cls.TYPE_BUSINESS,
                'price_ngn': 120000,
                'description': 'For business owners, directors, and corporate brands requiring company emblem branding, inquiry lead capture, and priority fulfillment.',
                'features': (
                    'Executive Laser-Engraved NFC Smart Card with Company Emblem\n'
                    'Verified Corporate Brand Profile with Company Identity\n'
                    'Direct Lead Capture Inquiry Box (Email & WhatsApp alert)\n'
                    'Interactive Google Maps Office Location & Operating Hours\n'
                    'Multi-Channel Social & Service Catalog Highlights\n'
                    'Advanced Profile Interaction & Visitor Insights\n'
                    'High-Priority Production (2-3 Business Days Dispatch)\n'
                    'Dedicated VIP Concierge & Setup Assistance'
                ),
                'badge': 'Best for Business',
                'is_active': True,
                'order_index': 3,
            },
            {
                'code': 'corporate-fleet',
                'name': 'Corporate Team Fleet',
                'package_type': cls.TYPE_CORPORATE,
                'price_ngn': 280000,
                'description': 'For corporate organizations, executive boards, and sales teams ordering 10 cards with centralized management and unified company branding.',
                'features': (
                    '10 Custom Laser-Engraved NFC Cards with Company Branding\n'
                    'Centralized Company Management Portal\n'
                    'Standardized Corporate Identity for All Staff\n'
                    'Team Tap, Engagement & Networking Analytics\n'
                    'Rapid Card Reassignment for New Employees\n'
                    'Dedicated Corporate Account Manager & Priority Support\n'
                    'Luxury Presentation Gift Box Packaging\n'
                    'Free Express Delivery for Whole Fleet'
                ),
                'badge': 'Enterprise Fleet',
                'is_active': True,
                'order_index': 4,
            },
        ]

        has_active = cls.objects.filter(is_active=True).exists()
        if force or not has_active:
            for pdata in defaults:
                cls.objects.update_or_create(code=pdata['code'], defaults=pdata)
            # Deactivate legacy packages if they exist to keep list clean
            cls.objects.filter(code__in=['starter', 'personal', 'business', 'business-pro']).update(is_active=False)


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
