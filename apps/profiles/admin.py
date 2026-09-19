from django.contrib import admin
from .models import Profile, SocialLink, CustomLink

class SocialLinkInline(admin.TabularInline):
    model = SocialLink
    extra = 1

class CustomLinkInline(admin.TabularInline):
    model = CustomLink
    extra = 1

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'slug', 'profile_type', 'phone', 'theme', 'is_search_indexed', 'created_at')
    list_filter = ('profile_type', 'theme', 'is_search_indexed', 'created_at')
    search_fields = ('full_name', 'user__email', 'slug', 'title', 'business_name', 'phone')
    prepopulated_fields = {'slug': ('full_name',)}
    inlines = [SocialLinkInline, CustomLinkInline]

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
