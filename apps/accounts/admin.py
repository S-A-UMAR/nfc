from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from .models import User, Referral, ReferralReward

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone', 'password', 'is_staff', 'is_active')}
        ),
    )


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        'referrer_email', 'referred_user_email', 'status',
        'has_qualifying_order', 'has_activation_card', 'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'referrer__email', 'referred_user__email', 'code_used',
    )
    readonly_fields = (
        'referrer', 'referred_user', 'code_used', 'created_at',
        'verified_at', 'qualified_at', 'qualifying_order', 'activation_card',
        'reward_amount_ngn',
    )
    ordering = ('-created_at',)
    list_select_related = ('referrer', 'referred_user', 'qualifying_order', 'activation_card')

    def referrer_email(self, obj):
        return obj.referrer.email
    referrer_email.short_description = 'Referrer'
    referrer_email.admin_order_field = 'referrer__email'

    def referred_user_email(self, obj):
        return obj.referred_user.email
    referred_user_email.short_description = 'Referred User'
    referred_user_email.admin_order_field = 'referred_user__email'

    def has_qualifying_order(self, obj):
        return obj.qualifying_order_id is not None
    has_qualifying_order.boolean = True
    has_qualifying_order.short_description = 'Paid Order?'

    def has_activation_card(self, obj):
        return obj.activation_card_id is not None
    has_activation_card.boolean = True
    has_activation_card.short_description = 'Card Activated?'

    actions = ['mark_rejected']

    def mark_rejected(self, request, queryset):
        updated = queryset.exclude(
            status=Referral.STATUS_REJECTED
        ).update(status=Referral.STATUS_REJECTED)
        self.message_user(request, f"{updated} referral(s) marked as rejected.")
    mark_rejected.short_description = "Mark selected referrals as Rejected"


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = (
        'referrer_email', 'status', 'created_at',
        'reviewed_by_email', 'reviewed_at', 'claimed_at', 'fulfilled_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('referrer__email',)
    readonly_fields = (
        'referrer', 'triggering_referral', 'triggering_card',
        'created_at', 'reviewed_at', 'claimed_at', 'fulfilled_at',
        'delivery_name', 'delivery_phone', 'delivery_address',
        'delivery_city', 'delivery_state',
    )
    ordering = ('-created_at',)
    list_select_related = ('referrer', 'reviewed_by')

    fieldsets = (
        ('Reward Identity', {
            'fields': ('referrer', 'status', 'triggering_referral', 'triggering_card'),
        }),
        ('Admin Review', {
            'fields': ('reviewed_by', 'reviewed_at', 'admin_notes'),
        }),
        ('Delivery Information (Customer-Provided)', {
            'fields': (
                'delivery_name', 'delivery_phone', 'delivery_address',
                'delivery_city', 'delivery_state',
            ),
        }),
        ('Fulfilment', {
            'fields': ('free_card_assigned', 'claimed_at', 'fulfilled_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )

    def referrer_email(self, obj):
        return obj.referrer.email
    referrer_email.short_description = 'Referrer'
    referrer_email.admin_order_field = 'referrer__email'

    def reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else '—'
    reviewed_by_email.short_description = 'Reviewed By'

    actions = ['approve_reward', 'make_available', 'mark_fulfilled', 'reject_reward']

    def approve_reward(self, request, queryset):
        updated = queryset.filter(
            status=ReferralReward.STATUS_PENDING_REVIEW
        ).update(
            status=ReferralReward.STATUS_APPROVED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} reward(s) approved.")
    approve_reward.short_description = "✅ Approve selected rewards (Pending → Approved)"

    def make_available(self, request, queryset):
        updated = queryset.filter(
            status=ReferralReward.STATUS_APPROVED
        ).update(
            status=ReferralReward.STATUS_AVAILABLE,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} reward(s) set to Available.")
    make_available.short_description = "🎁 Make selected rewards Available to Claim"

    def mark_fulfilled(self, request, queryset):
        updated = queryset.filter(
            status=ReferralReward.STATUS_CLAIMED
        ).update(
            status=ReferralReward.STATUS_FULFILLED,
            fulfilled_at=timezone.now(),
        )
        self.message_user(request, f"{updated} reward(s) marked as Fulfilled.")
    mark_fulfilled.short_description = "📦 Mark selected rewards as Fulfilled (card dispatched)"

    def reject_reward(self, request, queryset):
        updated = queryset.exclude(
            status__in=[ReferralReward.STATUS_FULFILLED, ReferralReward.STATUS_REJECTED]
        ).update(
            status=ReferralReward.STATUS_REJECTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f"{updated} reward(s) rejected.")
    reject_reward.short_description = "❌ Reject selected rewards"
