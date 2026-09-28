from django.contrib import admin
from .models import AnalyticsEvent


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    """Admin registration for AnalyticsEvent with search, filter, and display config."""
    list_display = ('id', 'event_type', 'target_label', 'profile', 'card', 'website', 'timestamp')
    list_filter = ('event_type', 'timestamp')
    search_fields = ('event_type', 'profile__full_name', 'card__card_code')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'
