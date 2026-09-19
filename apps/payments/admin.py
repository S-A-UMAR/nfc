from django.contrib import admin
from django.utils.html import format_html
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order', 'amount_display', 'status_badge', 'provider', 'channel', 'paid_at', 'created_at')
    list_filter = ('status', 'provider', 'created_at')
    search_fields = ('reference', 'order__order_number', 'order__user__email', 'paystack_access_code')

    def amount_display(self, obj):
        return f"₦{obj.amount:,.0f}"
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        color = '#10B981' if obj.status == 'success' else ('#EF4444' if obj.status == 'failed' else '#F59E0B')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'
