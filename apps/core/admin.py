from django.contrib import admin
from .models import ContactMessage, AdminAuditLog, BusinessInquiry

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'full_name', 'email', 'phone', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'created_at')
    search_fields = ('subject', 'full_name', 'email', 'message')
    list_editable = ('is_resolved',)


@admin.register(BusinessInquiry)
class BusinessInquiryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company_name', 'email', 'business_type', 'service_type', 'estimated_card_quantity', 'needs_website', 'status', 'created_at')
    list_filter = ('status', 'service_type', 'business_type', 'needs_website', 'created_at')
    search_fields = ('full_name', 'company_name', 'email', 'phone', 'message')
    list_editable = ('status',)
    readonly_fields = ('ip_address', 'created_at', 'updated_at')
    fieldsets = (
        ('Contact Details', {
            'fields': ('full_name', 'company_name', 'email', 'phone'),
        }),
        ('Inquiry Details', {
            'fields': ('business_type', 'service_type', 'estimated_card_quantity', 'needs_website', 'message'),
        }),
        ('Pipeline', {
            'fields': ('status', 'admin_notes', 'assigned_staff'),
        }),
        ('Metadata', {
            'fields': ('ip_address', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'target_repr', 'staff_user', 'previous_state', 'new_state', 'ip_address', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('target_repr', 'staff_user__email', 'details')
    readonly_fields = ('action', 'staff_user', 'target_repr', 'target_model', 'target_id', 'previous_state', 'new_state', 'details', 'ip_address', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
