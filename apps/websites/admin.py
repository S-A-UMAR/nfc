from django.contrib import admin
from django.utils.html import format_html
from .models import Website, WebsiteChangeRequest, Service, Product

class WebsiteChangeRequestInline(admin.StackedInline):
    model = WebsiteChangeRequest
    extra = 0

class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0

class ProductInline(admin.TabularInline):
    model = Product
    extra = 0

@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'user', 'website_type', 'template_choice', 'status_badge', 'created_at')
    list_filter = ('status', 'website_type', 'template_choice', 'created_at')
    search_fields = ('title', 'slug', 'domain', 'user__email', 'user__first_name')
    inlines = [ServiceInline, ProductInline, WebsiteChangeRequestInline]
    prepopulated_fields = {'slug': ('title',)}

    def status_badge(self, obj):
        colors = {
            'published': '#10B981',
            'draft': '#F59E0B',
            'unpublished': '#9A9A9A',
            'maintenance': '#EF4444',
            # Legacy fallback
            'live': '#10B981',
            'designing': '#F59E0B',
            'review': '#3B82F6',
            'provisioning': '#9A9A9A',
        }
        color = colors.get(obj.status, '#9A9A9A')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'website', 'price', 'is_active', 'display_order')
    list_filter = ('is_active', 'website')
    search_fields = ('name', 'description', 'website__title')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'website', 'price', 'is_active', 'display_order')
    list_filter = ('is_active', 'website')
    search_fields = ('name', 'description', 'website__title')


@admin.register(WebsiteChangeRequest)
class WebsiteChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('subject', 'website', 'user', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('subject', 'message', 'website__title', 'user__email')
    list_editable = ('status',)
