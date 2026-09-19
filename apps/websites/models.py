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

    STATUS_PROVISIONING = 'provisioning'
    STATUS_DESIGNING = 'designing'
    STATUS_REVIEW = 'review'
    STATUS_LIVE = 'live'
    STATUS_MAINTENANCE = 'maintenance'

    STATUS_CHOICES = (
        (STATUS_PROVISIONING, 'Setting up Environment'),
        (STATUS_DESIGNING, 'In Custom Design'),
        (STATUS_REVIEW, 'Client Review'),
        (STATUS_LIVE, 'Active & Live'),
        (STATUS_MAINTENANCE, 'Maintenance Mode'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='websites')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='websites')
    website_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_BUSINESS)
    template_choice = models.CharField(max_length=50, choices=TEMPLATE_CHOICES, default='modern_business')
    title = models.CharField(max_length=150)
    domain = models.CharField(max_length=150, blank=True, help_text="e.g. www.ahmedphones.com or ahmed.ulva.io")
    live_url = models.URLField(blank=True, help_text="Full external live link")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DESIGNING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.domain or 'Pending Domain'}) - {self.get_status_display()}"


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
