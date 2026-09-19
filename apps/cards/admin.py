from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from .models import Card, CardEvent

@admin.action(description="Batch Generate 20 Sequential Cards (Unassigned)")
def batch_generate_20_cards(modeladmin, request, queryset):
    # Find highest existing code
    existing = Card.objects.filter(card_code__startswith='BR-').order_by('-card_code').first()
    start_num = 1
    if existing:
        try:
            start_num = int(existing.card_code.replace('BR-', '')) + 1
        except ValueError:
            start_num = Card.objects.count() + 1
            
    created_count = 0
    for i in range(20):
        code = f"BR-{start_num + i:06d}"
        if not Card.objects.filter(card_code=code).exists():
            Card.objects.create(card_code=code, status=Card.STATUS_UNASSIGNED)
            created_count += 1
            
    messages.success(request, f"Successfully created {created_count} new unassigned cards in batch.")


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('card_code', 'status_badge', 'user', 'profile', 'material', 'qr_preview', 'created_at', 'activated_at')
    list_filter = ('status', 'material', 'created_at')
    search_fields = ('card_code', 'user__email', 'user__first_name', 'profile__full_name')
    actions = [batch_generate_20_cards]
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
