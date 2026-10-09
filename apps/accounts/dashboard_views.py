from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from apps.profiles.models import Profile
from apps.cards.models import Card
from apps.orders.models import Order
from apps.analytics.models import AnalyticsEvent
from apps.websites.models import Website
from .forms import UserUpdateForm
from datetime import timedelta
from django.utils import timezone

from django.db.models import Count, Q

@login_required
def dashboard_overview_view(request):
    """
    Main Dashboard Overview — all stats and deltas are calculated directly from DB in optimized queries.
    """
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'full_name': request.user.display_name, 'email': request.user.email}
    )

    primary_card = Card.objects.filter(user=request.user).order_by('activated_at').first()
    orders = Order.objects.filter(user=request.user).select_related('package').order_by('-created_at')[:4]
    primary_website = Website.objects.filter(user=request.user).first()

    # Time boundaries for deltas
    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    # Perform a single optimized aggregate query for all total counts and 7d/14d deltas
    stats = AnalyticsEvent.objects.filter(profile=profile).aggregate(
        profile_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW)),
        card_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN])),
        whatsapp_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP)),
        website_visits=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE)),
        
        recent_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW, timestamp__gte=seven_days_ago)),
        prev_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN], timestamp__gte=seven_days_ago)),
        prev_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN], timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_whatsapp=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP, timestamp__gte=seven_days_ago)),
        prev_whatsapp=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_website=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE, timestamp__gte=seven_days_ago)),
        prev_website=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
    )

    def calc_delta(recent, prev):
        if prev == 0:
            return round((recent / 1.0) * 100) if recent > 0 else 0
        return round(((recent - prev) / prev) * 100)

    return render(request, 'dashboard/overview.html', {
        'profile': profile,
        'primary_card': primary_card,
        'orders': orders,
        'primary_website': primary_website,
        'profile_views': stats['profile_views'] or 0,
        'card_taps': stats['card_taps'] or 0,
        'whatsapp_clicks': stats['whatsapp_clicks'] or 0,
        'website_visits': stats['website_visits'] or 0,
        'profile_views_delta': calc_delta(stats['recent_views'] or 0, stats['prev_views'] or 0),
        'card_taps_delta': calc_delta(stats['recent_taps'] or 0, stats['prev_taps'] or 0),
        'whatsapp_delta': calc_delta(stats['recent_whatsapp'] or 0, stats['prev_whatsapp'] or 0),
        'website_delta': calc_delta(stats['recent_website'] or 0, stats['prev_website'] or 0),
    })


@login_required
def settings_view(request):
    """Customer Account Settings & Password change with email alerts and safe email updates."""
    from apps.core.services.email_service import BrevoEmailService

    user_form = UserUpdateForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        if 'update_account' in request.POST:
            old_email = request.user.email
            user_form = UserUpdateForm(request.POST, instance=request.user)
            if user_form.is_valid():
                user = user_form.save()
                if user.email != old_email:
                    # Notify old email and send alert
                    BrevoEmailService.send_security_alert_email(
                        user, 
                        "Account Email Address Changed", 
                        f"The primary email address for your UZYRA account was changed from {old_email} to {user.email}."
                    )
                messages.success(request, "Account details updated successfully.")
                return redirect('dashboard:settings_view')
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                # Dispatch security notification email via Brevo
                BrevoEmailService.send_password_changed_notification(user)
                messages.success(request, "Password updated successfully. A security confirmation email has been sent.")
                return redirect('dashboard:settings_view')
            else:
                messages.error(request, "Please correct the errors in the password form.")

    return render(request, 'dashboard/settings.html', {
        'user_form': user_form,
        'password_form': password_form,
    })


@login_required
def delete_account_view(request):
    """
    Safe, verified Account Deletion flow conforming to NDPA 2023 (Right to Erasure).
    Requires password verification to prevent unauthorized account destruction.
    Sanitizes physical NFC cards, deletes profile, unpublishes websites, terminates session.
    """
    from django.contrib.auth import logout
    from apps.cards.models import Card
    from apps.websites.models import Website

    user = request.user

    if request.method == 'POST':
        confirm_acknowledged = request.POST.get('confirm_acknowledgment') == 'on'
        if not confirm_acknowledged:
            messages.error(request, "Please check the box confirming you understand the permanent consequences of deletion.")
            return render(request, 'dashboard/delete_account.html')

        # Password or email verification
        if user.has_usable_password():
            password = request.POST.get('confirm_password', '')
            if not password or not user.check_password(password):
                messages.error(request, "Incorrect password. For your security, account deletion has been cancelled.")
                return render(request, 'dashboard/delete_account.html')
        else:
            confirm_email = request.POST.get('confirm_email', '').strip().lower()
            if confirm_email != user.email.lower():
                messages.error(request, "Email verification did not match your account email address.")
                return render(request, 'dashboard/delete_account.html')

        # 1. Sanitize physical NFC cards: decouple from user/profile and reset to unassigned
        Card.objects.filter(user=user).update(
            user=None,
            profile=None,
            status=Card.STATUS_UNASSIGNED
        )

        # 2. Invalidate active session
        logout(request)

        # 3. Permanently delete user record (cascades profile, links, websites)
        user.delete()

        messages.success(request, "Your account and personal profile have been permanently deleted.")
        return redirect('core:home')

    return render(request, 'dashboard/delete_account.html')


@login_required
def dashboard_referrals_view(request):
    """
    Dashboard Referrals Overview (/dashboard/referrals/).
    Displays personal referral code, link, stats (verified, qualified),
    earned rewards balance, and referral history with privacy protection.
    """
    from .models import Referral
    from django.conf import settings
    from django.db.models import Sum

    user = request.user
    site_url = getattr(settings, 'SITE_URL', 'https://uzyra.com')
    referral_link = f"{site_url}/join/?ref={user.referral_code}"

    referrals = Referral.objects.filter(referrer=user).select_related('referred_user', 'qualifying_order')

    total_count = referrals.count()
    verified_count = referrals.filter(status__in=[Referral.STATUS_VERIFIED, Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED]).count()
    qualified_count = referrals.filter(status__in=[Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED]).count()
    
    total_rewards_ngn = referrals.filter(status__in=[Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED]).aggregate(
        total=Sum('reward_amount_ngn')
    )['total'] or 0

    # Privacy-conscious history formatting
    referral_history = []
    for ref in referrals:
        email = ref.referred_user.email
        parts = email.split('@')
        masked_email = f"{parts[0][0]}***@{parts[1]}" if len(parts) == 2 and len(parts[0]) > 0 else "User"
        referral_history.append({
            'masked_name': ref.referred_user.first_name or masked_email,
            'masked_email': masked_email,
            'status_display': ref.get_status_display(),
            'status': ref.status,
            'created_at': ref.created_at,
            'reward_ngn': ref.reward_amount_ngn if ref.status in (Referral.STATUS_QUALIFIED, Referral.STATUS_REWARDED) else 0,
        })

    return render(request, 'dashboard/referrals.html', {
        'user': user,
        'referral_code': user.referral_code,
        'referral_link': referral_link,
        'total_count': total_count,
        'verified_count': verified_count,
        'qualified_count': qualified_count,
        'total_rewards_ngn': total_rewards_ngn,
        'referral_history': referral_history,
    })


