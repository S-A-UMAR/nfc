import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
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



from django.db.models import Count, Q

@login_required
def analytics_dashboard_view(request):
    """Real-time analytics dashboard with 30-day breakdown and metrics in an optimized query."""
    profile = request.user.profile
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    counts = AnalyticsEvent.objects.filter(profile=profile, timestamp__gte=thirty_days_ago).aggregate(
        total_views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW)),
        views_7d=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW, timestamp__gte=seven_days_ago)),
        total_card_taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN])),
        total_whatsapp=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WHATSAPP)),
        total_calls=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_CALL)),
        total_vcards=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_VCARD)),
        total_websites=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_WEBSITE)),
    )

    recent_events = AnalyticsEvent.objects.filter(profile=profile, timestamp__gte=thirty_days_ago).order_by('-timestamp')[:25]

    return render(request, 'dashboard/analytics.html', {
        'profile': profile,
        'total_views': counts['total_views'] or 0,
        'views_7d': counts['views_7d'] or 0,
        'total_card_taps': counts['total_card_taps'] or 0,
        'total_whatsapp': counts['total_whatsapp'] or 0,
        'total_calls': counts['total_calls'] or 0,
        'total_vcards': counts['total_vcards'] or 0,
        'total_websites': counts['total_websites'] or 0,
        'recent_events': recent_events,
    })
