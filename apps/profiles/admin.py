from django.contrib import admin
from .models import (
    Profile, SocialLink, CustomLink, ContactExchange,
    ProfileService, ProfileGalleryItem, ProfileTestimonial
)

class SocialLinkInline(admin.TabularInline):
    model = SocialLink
    extra = 1

class CustomLinkInline(admin.TabularInline):
    model = CustomLink
    extra = 1

class ProfileServiceInline(admin.TabularInline):
    model = ProfileService
    extra = 1

class ProfileGalleryItemInline(admin.TabularInline):
    model = ProfileGalleryItem
    extra = 1

class ProfileTestimonialInline(admin.TabularInline):
    model = ProfileTestimonial
    extra = 1

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'slug', 'profile_type', 'phone', 'theme', 'is_search_indexed', 'created_at')
    list_filter = ('profile_type', 'theme', 'is_search_indexed', 'created_at')
    search_fields = ('full_name', 'user__email', 'slug', 'title', 'business_name', 'phone')
    prepopulated_fields = {'slug': ('full_name',)}
    inlines = [SocialLinkInline, CustomLinkInline, ProfileServiceInline, ProfileGalleryItemInline, ProfileTestimonialInline]

@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ('profile', 'platform', 'url', 'is_active', 'order')
    list_filter = ('platform', 'is_active')
    search_fields = ('profile__full_name', 'url')

@admin.register(CustomLink)
class CustomLinkAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'url', 'position', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('profile__full_name', 'title', 'url')

@admin.register(ProfileService)
class ProfileServiceAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'icon', 'order')
    search_fields = ('profile__full_name', 'title', 'description')

@admin.register(ProfileGalleryItem)
class ProfileGalleryItemAdmin(admin.ModelAdmin):
    list_display = ('profile', 'title', 'order')
    search_fields = ('profile__full_name', 'title')

@admin.register(ProfileTestimonial)
class ProfileTestimonialAdmin(admin.ModelAdmin):
    list_display = ('profile', 'client_name', 'client_title', 'rating', 'order')
    search_fields = ('profile__full_name', 'client_name', 'client_title', 'content')


@admin.register(ContactExchange)
class ContactExchangeAdmin(admin.ModelAdmin):
    """
    Contact Exchange — Staff Deletion Request Process
    --------------------------------------------------
    The Contact Exchange feature is currently DISABLED on all public profiles.
    Legacy records collected prior to disablement are stored here, restricted
    to authorised staff only. The customer-facing dashboard does NOT surface
    these records.

    Data Subject Deletion Requests:
        1. Requests arrive via the Complaints / Contact form with the subject
           prefix [Data Privacy Request].
        2. Identify the data subject: verify their name, email, and profile.
        3. Locate relevant records using the Search box above (search by email,
           phone, or name).
        4. Delete only the verified data subject's records using the Django Admin
           action "Delete selected contact exchange records".
        5. Reply to the data subject confirming deletion. Log the action in the
           platform's AdminAuditLog if available, or in your internal ops log.

    DO NOT modify, export, or bulk-delete records without an explicit verified
    request or a lawful authority directive.
    """
    list_display = ('full_name', 'profile', 'email', 'phone', 'business_name', 'is_read', 'consent_given', 'created_at')
    list_filter = ('is_read', 'consent_given', 'created_at')
    search_fields = ('full_name', 'email', 'phone', 'business_name', 'profile__full_name', 'notes')
    readonly_fields = ('profile', 'full_name', 'email', 'phone', 'business_name', 'notes',
                       'consent_given', 'ip_address', 'user_agent', 'created_at', 'is_read', 'read_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False  # Contacts are only created by visitors, never manually

    def has_change_permission(self, request, obj=None):
        return False  # Read-only in admin — deletion requests handled via delete action only
