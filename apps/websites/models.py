from django.db import models
from django.conf import settings
from apps.orders.models import Order

class Website(models.Model):
    TYPE_PERSONAL = 'personal'
    TYPE_BUSINESS = 'business'
    
    TYPE_CHOICES = (
        (TYPE_PERSONAL, 'Personal Brand Website'),
        (TYPE_BUSINESS, 'Corporate Business Website'),
    )

    TEMPLATE_CHOICES = (
        ('modern_business', 'Template 01 — Modern Business & Services'),
        ('luxury_atelier', 'Template 02 — Luxury Brand & Atelier'),
        ('creator_portfolio', 'Template 03 — Creator & Professional Portfolio'),
        ('retail_showcase', 'Template 04 — Retail & Product Showcase'),
    )

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_UNPUBLISHED = 'unpublished'
    STATUS_MAINTENANCE = 'maintenance'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft / Designing'),
        (STATUS_PUBLISHED, 'Published & Live'),
        (STATUS_UNPUBLISHED, 'Unpublished'),
        (STATUS_MAINTENANCE, 'Maintenance Mode'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='websites')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='websites')
    website_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_BUSINESS)
    template_choice = models.CharField(max_length=50, choices=TEMPLATE_CHOICES, default='modern_business')
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True, blank=True, null=True)
    domain = models.CharField(max_length=150, blank=True, help_text="e.g. www.ahmedphones.com or ahmed.ulva.io")
    live_url = models.URLField(blank=True, help_text="Full external live link")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    # Section Toggles
    show_hero = models.BooleanField(default=True)
    show_about = models.BooleanField(default=True)
    show_services = models.BooleanField(default=True)
    show_products = models.BooleanField(default=True)
    show_gallery = models.BooleanField(default=False)
    show_social = models.BooleanField(default=True)
    show_contact = models.BooleanField(default=True)
    show_footer = models.BooleanField(default=True)
    
    # Brand Customization
    primary_color = models.CharField(max_length=20, default="#000000")
    secondary_color = models.CharField(max_length=20, default="#ffffff")
    button_style = models.CharField(max_length=20, choices=[('solid', 'Solid'), ('outline', 'Outline'), ('rounded', 'Rounded')], default='solid')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.slug or 'No slug'}) - {self.get_status_display()}"
        
    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            import uuid
            base_slug = slugify(self.title) or "site"
            slug = base_slug
            counter = 1
            while Website.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class WebsiteChangeRequest(models.Model):
    STATUS_SUBMITTED = 'submitted'
    STATUS_REVIEW = 'in_review'
    STATUS_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = (
        (STATUS_SUBMITTED, 'Request Submitted'),
        (STATUS_REVIEW, 'Under Review'),
        (STATUS_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Changes Applied & Live'),
    )

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='change_requests')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='website_change_requests')
    subject = models.CharField(max_length=200)
    message = models.TextField(help_text="Describe the exact text, images, or updates you would like made.")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    admin_response = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Change Request #{self.id} on {self.website.title} [{self.get_status_display()}]"
class Service(models.Model):
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='websites/services/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.name} - {self.website.title}"


class Product(models.Model):
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    price = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='websites/products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.name} - {self.website.title}"
