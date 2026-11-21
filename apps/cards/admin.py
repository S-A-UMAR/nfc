from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from .models import Card, CardEvent

@admin.action(description="Batch Generate 20 Random ST- Cards (Warehouse Stock)")
def batch_generate_20_cards(modeladmin, request, queryset):
    from .services.card_generator import create_card_batch
    cards, token = create_card_batch(count=20, material='matte_black', staff_user=request.user)
    messages.success(
        request, 
        f"Successfully created {len(cards)} new warehouse stock cards (ST-XXXXXXXX format). "
        f"Packaging manifest token: {token[:8]}... (accessible in STRIDE Console)."
    )


@admin.action(description="Mark selected cards as Warehouse Stock (Locked)")
def mark_as_warehouse_stock(modeladmin, request, queryset):
    updated = queryset.filter(status=Card.STATUS_UNASSIGNED).update(is_warehouse_stock=True)
    messages.success(request, f"Marked {updated} unassigned card(s) as warehouse stock.")


@admin.action(description="Release selected cards from Warehouse Stock (Allow Self-Activation)")
def release_from_warehouse_stock(modeladmin, request, queryset):
    updated = queryset.update(is_warehouse_stock=False)
    messages.success(request, f"Released {updated} card(s) from warehouse stock locking.")


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('card_code', 'status_badge', 'provisioning_stage', 'batch_reference', 'is_warehouse_stock', 'user', 'profile', 'material', 'qr_preview', 'created_at', 'activated_at')
    list_filter = ('status', 'provisioning_stage', 'is_warehouse_stock', 'material', 'created_at')
    search_fields = ('card_code', 'batch_reference', 'user__email', 'user__first_name', 'profile__full_name')
    actions = [batch_generate_20_cards, mark_as_warehouse_stock, release_from_warehouse_stock]
    readonly_fields = ('qr_preview', 'created_at')

    def status_badge(self, obj):
        colors = {
            'ACTIVE': '#10B981',
            'UNASSIGNED': '#9A9A9A',
            'RESERVED': '#3B82F6',
            'LOST': '#EF4444',
            'SUSPENDED': '#F59E0B',
            'REPLACED': '#6B7280',
        }
        color = colors.get(obj.status, '#9A9A9A')
        return format_html('<span style="color: {}; font-weight: bold;">● {}</span>', color, obj.get_status_display())
    status_badge.short_description = 'Status'

    def qr_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="40" height="40" style="border-radius: 4px;" />', obj.qr_code_image.url)
        return "-"
    qr_preview.short_description = 'QR'


@admin.register(CardEvent)
class CardEventAdmin(admin.ModelAdmin):
    list_display = ('card', 'event_type', 'created_at', 'user_agent')
    list_filter = ('event_type', 'created_at')
    search_fields = ('card__card_code', 'user_agent')
