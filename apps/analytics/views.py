import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta, date
from django.db.models import Count, Q
from .models import AnalyticsEvent
from apps.profiles.models import Profile

import logging
logger = logging.getLogger('uzyra.analytics')

ALLOWED_EVENT_TYPES = {choice[0] for choice in AnalyticsEvent.TYPE_CHOICES}


@csrf_exempt
@require_POST
def track_event_api(request):
    """
    Asynchronous beacon endpoint to record anonymous clicks & interactions on public profiles.
    Strictly validates input, bounds payloads, and prevents internal exception leakage.
    """
    from apps.core.security import check_rate_limit, get_client_ip

    ip = get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(f"analytics_beacon:{ip}", limit=120, window_seconds=60)
    if not allowed:
        return JsonResponse({'status': 'error', 'message': 'Rate limit exceeded'}, status=429)

    try:
        data = json.loads(request.body)
        slug = data.get('profile_slug')
        event_type = data.get('event_type')
        target_label = data.get('target_label', '')

        if not slug or not event_type:
            return JsonResponse({'status': 'error', 'message': 'Missing slug or event type'}, status=400)

        if event_type not in ALLOWED_EVENT_TYPES:
            return JsonResponse({'status': 'error', 'message': 'Invalid event type'}, status=400)

        profile = Profile.objects.filter(slug=slug).first()
        if not profile:
            return JsonResponse({'status': 'error', 'message': 'Profile not found'}, status=404)

        AnalyticsEvent.objects.create(
            profile=profile,
            event_type=event_type,
            target_label=str(target_label)[:150],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
            referer=request.META.get('HTTP_REFERER', '')[:255]
        )
        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error in track_event_api: {e}")
        return JsonResponse({'status': 'error', 'message': 'An error occurred while logging interaction'}, status=500)


@csrf_exempt
@require_POST
def website_cta_track_view(request):
    """
    Beacon endpoint for website CTA button clicks.
    Accepts JSON: { "website_slug": "...", "target_label": "..." }
    """
    from apps.core.security import check_rate_limit, get_client_ip
    from apps.websites.models import Website

    ip = get_client_ip(request)
    allowed, remaining, retry_after = check_rate_limit(f"website_cta:{ip}", limit=120, window_seconds=60)
    if not allowed:
        return JsonResponse({'status': 'error', 'message': 'Rate limit exceeded'}, status=429)

    try:
        data = json.loads(request.body)
        website_slug = data.get('website_slug', '').strip()
        target_label = data.get('target_label', '')

        if not website_slug:
            return JsonResponse({'status': 'error', 'message': 'Missing website_slug'}, status=400)

        website = Website.objects.filter(slug=website_slug, status=Website.STATUS_PUBLISHED).first()
        if not website:
            return JsonResponse({'status': 'error', 'message': 'Website not found'}, status=404)

        try:
            profile = website.user.profile
        except Exception:
            profile = None

        AnalyticsEvent.objects.create(
            profile=profile,
            website=website,
            event_type=AnalyticsEvent.TYPE_WEBSITE_CTA_CLICK,
            target_label=str(target_label)[:150],
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
            referer=request.META.get('HTTP_REFERER', '')[:255],
        )
        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error in website_cta_track_view: {e}")
        return JsonResponse({'status': 'error', 'message': 'An error occurred'}, status=500)


# ---------------------------------------------------------------------------
# Analytics Dashboard View
# ---------------------------------------------------------------------------

RANGE_OPTIONS = {
    '7': 7,
    '30': 30,
    '90': 90,
    'all': None,
}

INTERACTION_LABELS = {
    AnalyticsEvent.TYPE_CARD_TAP: 'NFC Card Tap',
    AnalyticsEvent.TYPE_QR_SCAN: 'QR Scan',
    AnalyticsEvent.TYPE_WHATSAPP: 'WhatsApp Click',
    AnalyticsEvent.TYPE_CALL: 'Phone Click',
    AnalyticsEvent.TYPE_EMAIL: 'Email Click',
    AnalyticsEvent.TYPE_WEBSITE: 'Website Click',
    AnalyticsEvent.TYPE_SOCIAL: 'Social Click',
    AnalyticsEvent.TYPE_VCARD: 'vCard Save',
    AnalyticsEvent.TYPE_WEBSITE_CTA_CLICK: 'Website CTA Click',
}


@login_required
def analytics_dashboard_view(request):
    """
    Analytics dashboard with date-range filtering, per-card breakdown,
    per-website breakdown, and a pure-CSS bar chart of daily activity.
    All queries are strictly scoped to request.user.profile.
    """
    profile = request.user.profile
    now = timezone.now()

    # --- Date range ---
    range_param = request.GET.get('range', '30')
    if range_param not in RANGE_OPTIONS:
        range_param = '30'
    days = RANGE_OPTIONS[range_param]

    if days is not None:
        since = now - timedelta(days=days)
        base_qs = AnalyticsEvent.objects.filter(profile=profile, timestamp__gte=since)
    else:
        since = None
        base_qs = AnalyticsEvent.objects.filter(profile=profile)

    # --- Aggregate counts ---
    counts = base_qs.aggregate(
        card_taps=Count('id', filter=Q(event_type__in=[
            AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN
        ])),
        profile_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW)),
        website_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE_PAGE_VIEW)),
        whatsapp_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP)),
        phone_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_CALL)),
        email_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_EMAIL)),
        social_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_SOCIAL)),
        vcard_downloads=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_VCARD)),
        website_cta_clicks=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE_CTA_CLICK)),
    )

    total_link_clicks = (
        counts['card_taps'] +
        counts['whatsapp_clicks'] +
        counts['phone_clicks'] +
        counts['email_clicks'] +
        counts['social_clicks'] +
        counts['vcard_downloads'] +
        counts['website_cta_clicks']
    )

    # --- Top interaction type ---
    top_interaction = None
    top_count = 0
    interaction_totals = {
        AnalyticsEvent.TYPE_CARD_TAP: counts['card_taps'],
        AnalyticsEvent.TYPE_WHATSAPP: counts['whatsapp_clicks'],
        AnalyticsEvent.TYPE_CALL: counts['phone_clicks'],
        AnalyticsEvent.TYPE_EMAIL: counts['email_clicks'],
        AnalyticsEvent.TYPE_SOCIAL: counts['social_clicks'],
        AnalyticsEvent.TYPE_VCARD: counts['vcard_downloads'],
        AnalyticsEvent.TYPE_WEBSITE_CTA_CLICK: counts['website_cta_clicks'],
    }
    for event_key, event_count in interaction_totals.items():
        if event_count > top_count:
            top_count = event_count
            top_interaction = INTERACTION_LABELS.get(event_key, event_key)

    # --- Daily chart data (last N days or last 90 for 'all') ---
    chart_days = days if days is not None else 90
    chart_since = now - timedelta(days=chart_days)
    chart_qs = AnalyticsEvent.objects.filter(profile=profile, timestamp__gte=chart_since)

    # Build date bucket list
    daily_counts = {}
    for i in range(chart_days - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        daily_counts[d] = 0

    # Count events per day
    from django.db.models.functions import TruncDate
    day_aggregates = (
        chart_qs
        .annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(count=Count('id'))
    )
    for row in day_aggregates:
        d = row['day']
        if d in daily_counts:
            daily_counts[d] = row['count']

    daily_chart = [
        {'date': d.strftime('%b %-d'), 'count': c, 'iso': d.isoformat()}
        for d, c in daily_counts.items()
    ]
    max_daily = max((item['count'] for item in daily_chart), default=1) or 1

    # --- Per-card breakdown ---
    from apps.cards.models import Card
    user_cards = Card.objects.filter(user=request.user)
    card_breakdown = []
    for card in user_cards:
        card_qs = base_qs.filter(card=card)
        tap_count = card_qs.filter(
            event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN]
        ).count()
        card_breakdown.append({
            'card': card,
            'tap_count': tap_count,
        })

    # --- Per-website breakdown ---
    from apps.websites.models import Website
    user_websites = Website.objects.filter(user=request.user)
    website_breakdown = []
    for website in user_websites:
        # website_page_view events reference website FK, but profile FK is also set
        site_view_count = AnalyticsEvent.objects.filter(
            website=website,
            event_type=AnalyticsEvent.TYPE_WEBSITE_PAGE_VIEW,
            **(({'timestamp__gte': since} if since else {}))
        ).count()
        website_breakdown.append({
            'website': website,
            'view_count': site_view_count,
        })

    # --- Range labels ---
    range_labels = {
        '7': '7 Days',
        '30': '30 Days',
        '90': '90 Days',
        'all': 'All Time',
    }

    return render(request, 'dashboard/analytics.html', {
        'profile': profile,
        # Counts
        'card_taps': counts['card_taps'],
        'profile_views': counts['profile_views'],
        'website_views': counts['website_views'],
        'whatsapp_clicks': counts['whatsapp_clicks'],
        'phone_clicks': counts['phone_clicks'],
        'email_clicks': counts['email_clicks'],
        'social_clicks': counts['social_clicks'],
        'vcard_downloads': counts['vcard_downloads'],
        'website_cta_clicks': counts['website_cta_clicks'],
        'total_link_clicks': total_link_clicks,
        # Chart
        'daily_chart': daily_chart,
        'max_daily': max_daily,
        # Breakdowns
        'card_breakdown': card_breakdown,
        'website_breakdown': website_breakdown,
        # Top stat
        'top_interaction': top_interaction,
        'top_count': top_count,
        # Range UI
        'current_range': range_param,
        'range_labels': range_labels,
    })
