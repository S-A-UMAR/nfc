from django.contrib import admin
from django.utils.html import format_html
from .models import Website, WebsiteChangeRequest

class WebsiteChangeRequestInline(admin.StackedInline):
    model = WebsiteChangeRequest
    extra = 0

@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'website_type', 'template_choice', 'domain', 'status_badge', 'created_at')
    list_filter = ('website_type', 'status', 'template_choice', 'created_at')
    search_fields = ('title', 'domain', 'user__email', 'user__first_name')
    inlines = [WebsiteChangeRequestInline]
    list_editable = ()

    def status_badge(self, obj):
        colors = {
            'live': '#10B981',
            'designing': '#F59E0B',
            'review': '#3B82F6',
            'provisioning': '#9A9A9A',
            'maintenance': '#EF4444',
        }
        color = colors.get(obj.status, '#9A9A9A')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'


@admin.register(WebsiteChangeRequest)
class WebsiteChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('subject', 'website', 'user', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('subject', 'message', 'website__title', 'user__email')
    list_editable = ('status',)
