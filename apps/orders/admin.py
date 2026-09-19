from django.contrib import admin
from django.utils.html import format_html
from .models import ProductPackage, Order, OrderRequirement

class OrderRequirementInline(admin.StackedInline):
    model = OrderRequirement
    can_delete = False
    extra = 0

@admin.register(ProductPackage)
class ProductPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'package_type', 'price_display', 'badge', 'is_active', 'order_index')
    list_filter = ('package_type', 'is_active')
    search_fields = ('name', 'code', 'description')
    list_editable = ('is_active', 'order_index', 'badge')
    prepopulated_fields = {'code': ('name',)}

    def price_display(self, obj):
        return f"₦{obj.price_ngn:,.0f}"
    price_display.short_description = 'Price (NGN)'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'package', 'amount_display', 'payment_badge', 'order_status', 'card_assigned', 'created_at')
    list_filter = ('payment_status', 'order_status', 'package', 'created_at')
    search_fields = ('order_number', 'user__email', 'user__first_name', 'shipping_name', 'shipping_phone')
    inlines = [OrderRequirementInline]
    list_editable = ('order_status',)

    def amount_display(self, obj):
        return f"₦{obj.amount:,.0f}"
    amount_display.short_description = 'Amount'

    def payment_badge(self, obj):
        color = '#10B981' if obj.payment_status == 'paid' else ('#EF4444' if obj.payment_status == 'failed' else '#F59E0B')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_payment_status_display())
    payment_badge.short_description = 'Payment'
