from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'order_link', 'amount_display', 'status_badge', 'provider', 'channel', 'paid_at', 'created_at')
    list_filter = ('status', 'provider', 'created_at')
    search_fields = ('reference', 'order__order_number', 'order__user__email', 'paystack_access_code')
    readonly_fields = ('reference', 'order', 'amount', 'paystack_access_code', 'raw_response', 'created_at', 'paid_at')

    def amount_display(self, obj):
        return f"₦{obj.amount:,.0f}"
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        colors = {
            Payment.STATUS_SUCCESS: '#10B981',
            Payment.STATUS_FAILED: '#EF4444',
            Payment.STATUS_CANCELLED: '#6B7280',
            Payment.STATUS_PENDING: '#F59E0B',
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'

    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:orders_order_change', args=[obj.order.pk])
            user_label = obj.order.user.email if obj.order.user else 'No User'
            return format_html('<a href="{}">#{} ({})</a>', url, obj.order.order_number, user_label)
        return "-"
    order_link.short_description = 'Order'
