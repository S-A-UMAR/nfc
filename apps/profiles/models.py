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
        ('graphite',  'STRIDE Default'),
        ('midnight',  'Midnight'),
        ('ocean',     'Ocean'),
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

    # Highlights, Tags & Social Proof
    skills_tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated skills or tags, e.g. Design, Product, Tech")
    languages = models.CharField(max_length=255, blank=True, help_text="Languages, e.g. English, Spanish, French")
    stat_experience = models.CharField(max_length=50, blank=True, default="5+ Years", help_text="e.g. 5+ Years")
    stat_projects = models.CharField(max_length=50, blank=True, default="50+ Projects", help_text="e.g. 50+ Projects")
    stat_followers = models.CharField(max_length=50, blank=True, default="10K+ Network", help_text="e.g. 10K+ Network / Clients")
    cta_banner_text = models.CharField(max_length=200, blank=True, default="Let's build something great together.")
    
    # Design & Visibility
    theme = models.CharField(max_length=25, choices=THEME_CHOICES, default='graphite')
    profile_layout = models.CharField(max_length=25, choices=LAYOUT_CHOICES, default='classic')
    is_search_indexed = models.BooleanField(default=True, help_text="Allow search engines to index profile")

    # Direct Link Mode (Bypass Profile to open single destination on tap)
    direct_link_enabled = models.BooleanField(
        default=False,
        help_text="When enabled, tapping your smart card immediately redirects visitors to your direct link"
    )
    direct_link_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Target URL for Direct Link Mode (e.g. LinkedIn, Instagram, WhatsApp, Calendly, Portfolio)"
    )
    direct_link_label = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Descriptive label, e.g. 'My LinkedIn', 'Instagram', 'Book Meeting'"
    )
    
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
    def skills_tag_list(self):
        if not self.skills_tags:
            if self.business_category:
                return [t.strip() for t in self.business_category.split(',') if t.strip()]
            return ["Design", "Product", "Tech"]
        return [t.strip() for t in self.skills_tags.split(',') if t.strip()]

    @property
    def language_list(self):
        if not self.languages:
            return ["English"]
        return [l.strip() for l in self.languages.split(',') if l.strip()]

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


class ProfileService(models.Model):
    """What I Do / Services offered by the profile owner."""
    ICON_CHOICES = (
        ('design', 'Product & Design'),
        ('consulting', 'Consulting & Strategy'),
        ('speaking', 'Speaking & Events'),
        ('code', 'Engineering & Tech'),
        ('camera', 'Media & Photography'),
        ('briefcase', 'Business & Management'),
        ('star', 'Specialist Service'),
    )

    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='services')
    title = models.CharField(max_length=150)
    description = models.CharField(max_length=255)
    icon = models.CharField(max_length=30, choices=ICON_CHOICES, default='design')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.title} ({self.profile.full_name})"


class ProfileGalleryItem(models.Model):
    """My Work / Portfolio gallery item."""
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='gallery_items')
    title = models.CharField(max_length=150, blank=True)
    image = models.ImageField(upload_to='profiles/gallery/', blank=True, null=True)
    image_url = models.URLField(blank=True, help_text="External or fallback image URL")
    link_url = models.URLField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.title or 'Gallery Item'} ({self.profile.full_name})"


class ProfileTestimonial(models.Model):
    """Client review or testimonial."""
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='testimonials')
    client_name = models.CharField(max_length=150)
    client_title = models.CharField(max_length=150, blank=True, help_text="e.g. Founder, ScaleUp")
    client_avatar = models.ImageField(upload_to='profiles/testimonials/', blank=True, null=True)
    content = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Review by {self.client_name} for {self.profile.full_name}"


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


class ContactExchange(models.Model):
    """
    Two-way contact exchange lead submitted by a visitor on a public STRIDE profile.
    Strictly isolated: viewable only by the receiving profile's owner.
    """
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='received_contacts')
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    business_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True, help_text="Optional note or context from visitor")
    consent_given = models.BooleanField(default=False, help_text="Explicit user consent given")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False, db_index=True, help_text="Whether the profile owner has viewed this contact")
    read_at = models.DateTimeField(null=True, blank=True, help_text="When the profile owner first viewed this contact")

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Exchange Lead'
        verbose_name_plural = 'Contact Exchange Leads'

    def __str__(self):
        return f"Lead: {self.full_name} -> {self.profile.full_name}"

    def mark_read(self):
        """Mark this contact as read if not already read."""
        if not self.is_read:
            from django.utils import timezone
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

