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
    Main Dashboard Overview Command Center — real database stats, card status,
    network leads, and contextual guidance in optimized queries.
    """
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'full_name': request.user.display_name, 'email': request.user.email}
    )

    # Cards query - evaluate once to avoid extra count queries
    cards = list(Card.objects.filter(user=request.user).select_related('profile').order_by('-activated_at', '-created_at'))
    primary_card = cards[0] if cards else None
    has_card = bool(primary_card)
    cards_count = len(cards)
    active_cards_count = sum(1 for c in cards if c.status == Card.STATUS_ACTIVE)

    # Orders query
    orders = Order.objects.filter(user=request.user).select_related('package').order_by('-created_at')[:4]
    active_order = Order.objects.filter(user=request.user).exclude(order_status__in=['completed', 'cancelled']).order_by('-created_at').first()
    primary_website = Website.objects.filter(user=request.user).first()

    has_slug = bool(profile.slug)
    has_contact = bool(profile.phone or profile.whatsapp or profile.email)
    has_links = profile.social_links.exists() or profile.custom_links.exists()

    # Real profile checklist calculations (only genuine database fields)
    has_headline = bool(profile.title or profile.business_name)
    has_bio = bool(profile.bio or profile.business_description)
    has_photo = bool(profile.profile_image or profile.business_logo)

    checklist = [
        {
            'key': 'identity',
            'label': 'Name & Public Handle',
            'desc': 'Your full name and unique public profile link',
            'done': bool(profile.full_name and profile.slug),
            'url': 'dashboard:profile_edit',
            'action': 'Edit Name & Slug',
        },
        {
            'key': 'headline',
            'label': 'Headline or Business Name',
            'desc': 'Your professional headline, role or enterprise identity',
            'done': has_headline,
            'url': 'dashboard:profile_edit',
            'action': 'Add Headline',
        },
        {
            'key': 'bio',
            'label': 'Bio or About Overview',
            'desc': 'A concise summary of what you do, offer or create',
            'done': has_bio,
            'url': 'dashboard:profile_edit',
            'action': 'Add Bio',
        },
        {
            'key': 'contact',
            'label': 'Direct Contact Info',
            'desc': 'Phone, WhatsApp, or primary email for direct 1-tap taps',
            'done': has_contact,
            'url': 'dashboard:profile_edit',
            'action': 'Add Contact',
        },
        {
            'key': 'photo',
            'label': 'Profile Photo or Logo',
            'desc': 'A high-resolution headshot or business logo',
            'done': has_photo,
            'url': 'dashboard:profile_edit',
            'action': 'Upload Photo',
        },
        {
            'key': 'links',
            'label': 'Social & Action Links',
            'desc': 'Interactive buttons for LinkedIn, WhatsApp, website, etc.',
            'done': has_links,
            'url': 'dashboard:links_manage',
            'action': 'Add Links',
        },
    ]
    completed_checklist_count = sum(1 for item in checklist if item['done'])
    total_checklist_count = len(checklist)
    completion_percentage = round((completed_checklist_count / total_checklist_count) * 100)
    next_step = next((item for item in checklist if not item['done']), None)
    is_profile_configured = bool(profile.slug and (profile.title or profile.business_name))

    # Network activity
    recent_contacts = profile.received_contacts.order_by('-created_at')[:5]
    received_contacts_count = profile.received_contacts.count()
    unread_contacts_count = profile.received_contacts.filter(is_read=False).count()

    # Time-based personalized greeting
    now = timezone.now()
    hour = now.hour
    if hour < 12:
        greeting_time = "Good morning"
    elif hour < 17:
        greeting_time = "Good afternoon"
    else:
        greeting_time = "Good evening"

    first_name = request.user.first_name or (profile.full_name.split()[0] if profile.full_name else request.user.display_name)
    greeting = f"{greeting_time}, {first_name}"

    # Primary recommended action
    if not is_profile_configured:
        primary_action = {
            'label': 'Complete Profile Setup',
            'desc': 'Finish your digital profile to generate your live link & QR code.',
            'url': 'dashboard:onboarding',
            'badge': 'Action Required',
            'badge_type': 'warning',
        }
    elif not has_links:
        primary_action = {
            'label': 'Add Social & Action Links',
            'desc': 'Connect WhatsApp, LinkedIn, or your website so visitors can connect instantly.',
            'url': 'dashboard:links_manage',
            'badge': 'Recommended',
            'badge_type': 'info',
        }
    elif not has_card:
        primary_action = {
            'label': 'Order Smart NFC Card',
            'desc': 'Get a premium matte obsidian or brushed silver card for physical 1-tap sharing.',
            'url': 'dashboard:card_manage',
            'badge': 'Hardware',
            'badge_type': 'neutral',
        }
    else:
        primary_action = {
            'label': 'Share Digital Profile',
            'desc': 'Your profile and smart card are active. Share your card via QR code or direct link.',
            'url': 'dashboard:share',
            'badge': 'Ready to Share',
            'badge_type': 'success',
        }

    # Time boundaries for deltas
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    # Perform a single optimized aggregate query for all total counts and 7d/14d deltas
    stats = AnalyticsEvent.objects.filter(profile=profile).aggregate(
        profile_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW)),
        card_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN])),
        contact_saves=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_VCARD)),
        whatsapp_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP)),
        website_visits=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE)),
        link_clicks=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_WEBSITE, AnalyticsEvent.TYPE_SOCIAL])),
        
        recent_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW, timestamp__gte=seven_days_ago)),
        prev_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN], timestamp__gte=seven_days_ago)),
        prev_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN], timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),

        recent_vcard=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_VCARD, timestamp__gte=seven_days_ago)),
        prev_vcard=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_VCARD, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_whatsapp=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP, timestamp__gte=seven_days_ago)),
        prev_whatsapp=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
        
        recent_website=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE, timestamp__gte=seven_days_ago)),
        prev_website=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE, timestamp__gte=fourteen_days_ago, timestamp__lt=seven_days_ago)),
    )

    def calc_delta(recent, prev):
        if prev == 0:
            return round((recent / 1.0) * 100) if recent > 0 else 0
        return round(((recent - prev) / prev) * 100)

    profile_views_count = stats['profile_views'] or 0
    card_taps_count = stats['card_taps'] or 0
    contact_saves_count = stats['contact_saves'] or 0
    whatsapp_clicks_count = stats['whatsapp_clicks'] or 0
    website_visits_count = stats['website_visits'] or 0
    link_clicks_count = stats['link_clicks'] or 0

    total_interactions = profile_views_count + card_taps_count + contact_saves_count + whatsapp_clicks_count + link_clicks_count

    return render(request, 'dashboard/overview.html', {
        'profile': profile,
        'cards': cards,
        'primary_card': primary_card,
        'cards_count': cards_count,
        'active_cards_count': active_cards_count,
        'orders': orders,
        'active_order': active_order,
        'primary_website': primary_website,
        'has_slug': has_slug,
        'has_contact': has_contact,
        'has_links': has_links,
        'has_card': has_card,
        'has_headline': has_headline,
        'has_bio': has_bio,
        'has_photo': has_photo,
        'checklist': checklist,
        'completed_checklist_count': completed_checklist_count,
        'total_checklist_count': total_checklist_count,
        'completion_percentage': completion_percentage,
        'next_step': next_step,
        'is_profile_configured': is_profile_configured,
        'greeting': greeting,
        'primary_action': primary_action,
        'recent_contacts': recent_contacts,
        'received_contacts_count': received_contacts_count,
        'unread_contacts_count': unread_contacts_count,
        'profile_views': profile_views_count,
        'card_taps': card_taps_count,
        'contact_saves': contact_saves_count,
        'whatsapp_clicks': whatsapp_clicks_count,
        'website_visits': website_visits_count,
        'link_clicks': link_clicks_count,
        'total_interactions': total_interactions,
        'profile_views_delta': calc_delta(stats['recent_views'] or 0, stats['prev_views'] or 0),
        'card_taps_delta': calc_delta(stats['recent_taps'] or 0, stats['prev_taps'] or 0),
        'contact_saves_delta': calc_delta(stats['recent_vcard'] or 0, stats['prev_vcard'] or 0),
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
                        f"The primary email address for your STRIDE account was changed from {old_email} to {user.email}."
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


