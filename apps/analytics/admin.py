from django.contrib import admin
from .models import AnalyticsEvent

@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'target_label', 'profile', 'card', 'timestamp', 'user_agent')
    list_filter = ('event_type', 'timestamp')
    search_fields = ('profile__full_name', 'card__card_code', 'target_label', 'user_agent')
    readonly_fields = ('timestamp',)
