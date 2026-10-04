from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid

class Profile(models.Model):
    PROFILE_TYPES = (
        ('personal', 'Personal Identity'),
        ('business', 'Business Profile'),
    )

    # ── Personal themes ──────────────────────────────────────────────────────
    # ── Business themes ──────────────────────────────────────────────────────
    THEME_CHOICES = (
        # Personal
        ('graphite',  'UZYRA Default'),
        ('midnight',  'Midnight'),
        ('ocean',     'Ocean'),
        ('violet',    'Violet'),
        ('emerald',   'Emerald'),
        ('rose',      'Rose'),
        ('arctic',    'Arctic'),
        ('sand',      'Sand'),
        # Business
        ('executive', 'Executive'),
        ('navy',      'Navy'),
        ('emerald_business', 'Emerald Business'),
        ('royal',     'Royal'),
        ('burgundy',  'Burgundy'),
        ('luxury',    'Luxury'),
        ('platinum',  'Platinum'),
    )

    LAYOUT_CHOICES = (
        # Personal layouts
        ('classic',     'Classic'),
        ('centered',    'Centered'),
        ('minimal_layout', 'Minimal'),
        ('social',      'Social'),
        ('card',        'Card'),
        # Business layouts
        ('executive_layout', 'Executive'),
        ('brand_header', 'Brand Header'),
        ('business_card', 'Business Card'),
        ('business_catalog', 'Business Catalog'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPES, default='personal')
    
    # Personal Info
    full_name = models.CharField(max_length=150)
    title = models.CharField(max_length=150, blank=True, help_text="e.g. Founder & Creative Director")
    bio = models.TextField(blank=True, help_text="Brief professional bio or business pitch")
    profile_image = models.ImageField(upload_to='profiles/avatars/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='profiles/covers/', blank=True, null=True)
    
    # Business Info
    business_name = models.CharField(max_length=150, blank=True)
    business_description = models.TextField(blank=True)
    business_logo = models.ImageField(upload_to='profiles/logos/', blank=True, null=True)
    business_category = models.CharField(max_length=100, blank=True, help_text="e.g. Technology, Real Estate, Fashion")
    
    # Direct Contact Hub
    phone = models.CharField(max_length=50, blank=True)
    whatsapp = models.CharField(max_length=50, blank=True, help_text="WhatsApp phone number with country code")
    email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    location = models.CharField(max_length=150, blank=True, help_text="e.g. Lagos, Nigeria")
    address = models.TextField(blank=True)
    
    # Design & Visibility
    theme = models.CharField(max_length=25, choices=THEME_CHOICES, default='graphite')
    profile_layout = models.CharField(max_length=25, choices=LAYOUT_CHOICES, default='classic')
    is_search_indexed = models.BooleanField(default=True, help_text="Allow search engines to index profile")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name or self.user.email

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.full_name or self.user.email.split('@')[0])
            if not base_slug:
                base_slug = f"user-{uuid.uuid4().hex[:6]}"
            slug = base_slug
            counter = 1
            while Profile.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def clean_whatsapp(self):
        """Clean phone for wa.me direct links."""
        if not self.whatsapp:
            return ""
        digits = "".join([c for c in self.whatsapp if c.isdigit()])
        return digits

    @property
    def clean_phone(self):
        """Clean phone for tel: links."""
        if not self.phone:
            return ""
        return self.phone.replace(" ", "").replace("-", "")


class SocialLink(models.Model):
    PLATFORM_CHOICES = (
        ('instagram', 'Instagram'),
        ('linkedin', 'LinkedIn'),
        ('x_twitter', 'X (Twitter)'),
        ('tiktok', 'TikTok'),
        ('facebook', 'Facebook'),
        ('youtube', 'YouTube'),
        ('github', 'GitHub'),
        ('whatsapp', 'WhatsApp Channel'),
        ('telegram', 'Telegram'),
        ('behance', 'Behance'),
        ('dribbble', 'Dribbble'),
        ('other', 'Other'),
    )

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='social_links')
    platform = models.CharField(max_length=30, choices=PLATFORM_CHOICES)
    url = models.CharField(max_length=300)
    display_label = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.get_platform_display()} - {self.profile.full_name}"


class CustomLink(models.Model):
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='custom_links')
    title = models.CharField(max_length=120)
    url = models.CharField(max_length=300)
    icon = models.CharField(max_length=50, default='link', help_text="Icon identifier (e.g., link, globe, briefcase, star, download, calendar)")
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.title} ({self.profile.full_name})"
