from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Card, CardEvent
from apps.analytics.models import AnalyticsEvent

def nfc_redirect_view(request, card_code):
    """
    The Core NFC Redirect Hub (/c/<card_code>/).
    When an NFC card or QR code is tapped/scanned:
    1. Look up the card code in the database.
    2. Check status (ACTIVE, UNASSIGNED, RESERVED, LOST, SUSPENDED, REPLACED).
    3. Filter owner taps & log non-owner events.
    4. Route appropriately with sensory feedback trigger (?tap=1 or ?scan=1).
    """
    try:
        card = Card.objects.select_related('profile', 'profile__user', 'user', 'replacement_for').get(card_code__iexact=card_code.strip())
    except Card.DoesNotExist:
        return render(request, 'cards/card_not_found.html', {'card_code': card_code}, status=404)

    # Detect whether visit originated from QR or NFC tap (via query param or user-agent)
    is_qr = request.GET.get('source') == 'qr'
    event_type = CardEvent.EVENT_QR if is_qr else CardEvent.EVENT_NFC

    # Check if visitor is the owner of this card/profile
    is_owner = False
    if request.user.is_authenticated:
        if (card.user and request.user == card.user) or (card.profile and card.profile.user and request.user == card.profile.user):
            is_owner = True
    if not is_owner and card.profile and (request.COOKIES.get(f'stride_owner_{card.profile.slug}') == '1' or request.COOKIES.get(f'uzyra_owner_{card.profile.slug}') == '1'):
        is_owner = True

    # Log Card Event only if visitor is not the owner
    if not is_owner:
        CardEvent.objects.create(
            card=card,
            event_type=event_type,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
        )

    # Status Routing Engine
    if card.status == Card.STATUS_ACTIVE:
        if card.profile and card.profile.slug:
            # Direct Link Mode: bypass full profile to open chosen destination immediately
            if card.profile.direct_link_enabled and card.profile.direct_link_url:
                if not is_owner:
                    label = card.profile.direct_link_label or card.profile.direct_link_url
                    AnalyticsEvent.objects.create(
                        profile=card.profile,
                        card=card,
                        event_type=AnalyticsEvent.TYPE_CARD_TAP if not is_qr else AnalyticsEvent.TYPE_QR_SCAN,
                        target_label=f"Direct Link: {label}"[:150],
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                        referer=request.META.get('HTTP_REFERER', '')[:255]
                    )
                response = redirect(card.profile.direct_link_url)
                if is_owner:
                    response.set_cookie(f'stride_owner_{card.profile.slug}', '1', max_age=365 * 24 * 3600, samesite='Lax')
                    response.set_cookie(f'uzyra_owner_{card.profile.slug}', '1', max_age=365 * 24 * 3600, samesite='Lax')
                return response

            # Standard Profile Route
            # Also log analytics event for the profile owner only for external taps
            if not is_owner:
                AnalyticsEvent.objects.create(
                    profile=card.profile,
                    card=card,
                    event_type=AnalyticsEvent.TYPE_CARD_TAP if not is_qr else AnalyticsEvent.TYPE_QR_SCAN,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                    referer=request.META.get('HTTP_REFERER', '')[:255]
                )
            target_url = reverse('profiles:public_profile', kwargs={'slug': card.profile.slug})
            response = redirect(target_url)
            # Short-lived sensory feedback cookie consumed upon profile load (30 seconds)
            response.set_cookie('stride_tap', '1', max_age=30, samesite='Lax')
            response.set_cookie('uzyra_tap', '1', max_age=30, samesite='Lax')
            if is_owner:
                response.set_cookie(f'stride_owner_{card.profile.slug}', '1', max_age=365 * 24 * 3600, samesite='Lax')
                response.set_cookie(f'uzyra_owner_{card.profile.slug}', '1', max_age=365 * 24 * 3600, samesite='Lax')
            return response
        else:
            return render(request, 'cards/card_unlinked.html', {'card': card})

    elif card.status == Card.STATUS_LOST:
        return render(request, 'cards/card_lost.html', {'card': card})

    elif card.status == Card.STATUS_SUSPENDED:
        return render(request, 'cards/card_suspended.html', {'card': card})

    elif card.status == Card.STATUS_REPLACED:
        if card.replacement_for:
            return redirect('cards:nfc_redirect', card_code=card.replacement_for.card_code)
        return render(request, 'cards/card_replaced.html', {'card': card})

    elif card.status in [Card.STATUS_UNASSIGNED, Card.STATUS_RESERVED]:
        return render(request, 'cards/card_unassigned.html', {'card': card})

    return render(request, 'cards/card_unassigned.html', {'card': card})


@login_required
def card_manage_view(request):
    """Customer Dashboard Smart Card management."""
    profile = request.user.profile
    cards = Card.objects.filter(user=request.user)
    primary_card = cards.first()
    just_activated_card = request.session.pop('just_activated_card', None)

    return render(request, 'dashboard/card_manage.html', {
        'profile': profile,
        'cards': cards,
        'primary_card': primary_card,
        'just_activated_card': just_activated_card,
    })


from django.db import transaction
import urllib.parse
from django.urls import resolve, Resolver404
from apps.core.security import check_rate_limit, get_client_ip, is_safe_redirect_url
from apps.core.services.email_service import BrevoEmailService


def _get_safe_activation_redirect(request, card_code=None):
    """
    Resolves a safe internal redirection destination for card activation error and return flows.
    Guards:
    1. Evaluates candidate URLs in order: request.POST.get('next'), request.META.get('HTTP_REFERER').
    2. Enforces host and scheme safety via is_safe_redirect_url().
    3. Rejects external schemes, external hosts, and protocol-relative URLs.
    4. Rejects URL-encoded path bypasses (e.g. %2f, %5c, %2e%2e), double slashes (//), backslashes, and path traversal (/../).
    5. Resolves candidate path against Django's URLconf and ensures it targets an intended destination:
       - cards:nfc_redirect (verifying card_code matches if provided)
       - cards:activation_success
    6. Falls back safely to dashboard:card_manage.
    """
    candidates = []
    post_next = request.POST.get('next')
    if post_next:
        candidates.append(post_next)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        candidates.append(referer)

    normalized_card_code = card_code.strip().upper() if (card_code and isinstance(card_code, str)) else None
    default_fallback = reverse('dashboard:card_manage')

    for candidate in candidates:
        if not candidate or not isinstance(candidate, str):
            continue
        candidate = candidate.strip()
        if not candidate:
            continue

        # Check for control characters or null bytes in candidate string
        if any(ord(c) < 32 or ord(c) == 127 for c in candidate):
            continue

        # Reject protocol-relative or backslash-prefixed evasions
        if candidate.startswith('//') or candidate.startswith('/\\') or candidate.startswith('\\\\'):
            continue

        # Parse candidate URL
        try:
            parsed = urllib.parse.urlsplit(candidate)
        except Exception:
            continue

        # Reject external netloc if present (allow only empty netloc or exact host match)
        if parsed.netloc and parsed.netloc != request.get_host():
            continue

        # Reject non-http(s) schemes if scheme is present
        if parsed.scheme and parsed.scheme not in ('http', 'https'):
            continue

        path = parsed.path
        if not path or not path.startswith('/'):
            continue

        # Verify against base safety validator
        if not is_safe_redirect_url(request, path):
            continue

        # Unquote path to detect encoded bypass attempts (%2f, %5c, %2e%2e, etc.)
        unquoted_path = urllib.parse.unquote(path)
        if any(ord(c) < 32 or ord(c) == 127 for c in unquoted_path):
            continue
        # Disallow double slashes, backslashes, or directory traversal
        if '//' in unquoted_path or '\\' in unquoted_path or '/../' in unquoted_path or unquoted_path.endswith('/..') or unquoted_path.startswith('/..'):
            continue

        # Resolve path against Django URLconf to ensure it is a valid, registered route
        try:
            match = resolve(path)
        except Resolver404:
            continue

        # Ensure destination is an intended activation/cards destination
        if match.app_name == 'cards' and match.url_name in ('nfc_redirect', 'activation_success'):
            dest_card_code = match.kwargs.get('card_code', '').strip().upper()
            # If a specific card_code is being activated, ensure redirect targets that same card
            if normalized_card_code and dest_card_code and dest_card_code != normalized_card_code:
                continue
            return path

    return default_fallback


@login_required
@require_POST
def card_activate_view(request):
    """
    Customer activates or links a physical card to their profile.
    Security protections:
    1. Layered rate-limiting: per-account, per-card-code, and per-IP (all fail closed with HTTP 503 during outages).
    2. Atomic transaction with select_for_update() to eliminate race conditions.
    3. Proof of physical ownership: secret activation PIN check (hyphen-tolerant).
    4. Status guards: Active, Suspended, Replaced, Lost cards rejected.
    5. Reassignment guards: Cannot reassign card belonging to another user.
    6. Warehouse inventory protection: Unallocated warehouse inventory cards (is_warehouse_stock=True)
       are blocked from customer self-activation until allocated/dispatched by operations staff.
       Unassigned cards not flagged as warehouse stock remain activatable for backward compatibility.
    7. Safe redirect validation: Activation destination is strictly validated to prevent open redirects.
    """
    ip = get_client_ip(request)
    user_id = request.user.id

    # Extract card_code early for per-card rate limit key and redirect resolution (before DB lock)
    card_code = request.POST.get('card_code', '').strip().upper()
    activation_code = request.POST.get('activation_code', '').strip()
    profile = request.user.profile

    redirect_target = _get_safe_activation_redirect(request, card_code=card_code)

    # --- Layered Rate Limiting (all checks before the DB lock) ---

    # 1. Per-card rate limit: max 5 activation attempts on a specific card per hour (across all users/IPs).
    #    Protects against distributed brute-force across multiple accounts targeting one card.
    allowed_card, _, retry_card = check_rate_limit(
        f"card_act_card:{card_code}", limit=5, window_seconds=3600, sensitive=True
    )
    if not allowed_card:
        messages.error(request, f"Too many activation attempts for this card. Please try again in {retry_card} seconds.")
        return redirect(redirect_target)

    # 2. Per-IP rate limit: max 10 activation attempts per IP per 10 minutes.
    #    Protects against a single host cycling through many card codes or accounts.
    allowed_ip, _, retry_ip = check_rate_limit(
        f"card_act_ip:{ip}", limit=10, window_seconds=600, sensitive=True
    )
    if not allowed_ip:
        messages.error(request, f"Too many activation attempts from your connection. Please try again in {retry_ip} seconds.")
        return redirect(redirect_target)

    # 3. Per-account rate limit: max 5 activation attempts per user per 10 minutes.
    #    Fail closed consistently with per-card and per-IP (sensitive=True).
    allowed, remaining, retry_after = check_rate_limit(
        f"card_act:{user_id}", limit=5, window_seconds=600, sensitive=True
    )
    if not allowed:
        messages.error(request, f"Too many failed card activation attempts. Throttled for {retry_after} seconds.")
        return redirect(redirect_target)

    if not card_code:
        messages.error(request, "Please enter the Card ID code.")
        return redirect(redirect_target)

    with transaction.atomic():
        try:
            card = Card.objects.select_for_update().get(card_code__iexact=card_code)
        except Card.DoesNotExist:
            messages.error(request, f"Card '{card_code}' was not found. Please check the code printed on the physical card.")
            return redirect(redirect_target)

        # Guard: Already active
        if card.status == Card.STATUS_ACTIVE:
            messages.error(request, f"Card '{card_code}' is already active and in use.")
            return redirect(redirect_target)

        # Guard: Suspended
        if card.status == Card.STATUS_SUSPENDED:
            messages.error(request, f"Card '{card_code}' is suspended. Suspended cards cannot be activated.")
            return redirect(redirect_target)

        # Guard: Replaced
        if card.status == Card.STATUS_REPLACED:
            messages.error(request, f"Card '{card_code}' has been replaced and cannot be reactivated.")
            return redirect(redirect_target)

        # Guard: Reported Lost
        if card.status == Card.STATUS_LOST:
            messages.error(request, f"Card '{card_code}' has been reported lost and cannot be activated.")
            return redirect(redirect_target)

        # Guard: Warehouse Inventory Protection
        # Cards marked as warehouse stock cannot be self-activated by customers until
        # they have been assigned to an order and dispatched by operations staff.
        if card.status == Card.STATUS_UNASSIGNED and getattr(card, 'is_warehouse_stock', False):
            messages.error(
                request,
                f"Card '{card_code}' is registered as unallocated warehouse inventory and cannot be activated yet. "
                "Please ensure your order has been processed and dispatched, or contact STRIDE support."
            )
            return redirect(redirect_target)

        # Guard: Assigned to another user
        if card.user and card.user != request.user:
            messages.error(request, f"Card '{card_code}' is already assigned to another account.")
            return redirect(redirect_target)

        # Guard: Activation PIN verification
        if not card.activation_code_hash:
            messages.error(
                request,
                f"Card '{card_code}' does not have an activation PIN configured. Please contact STRIDE support to activate this card."
            )
            return redirect(redirect_target)

        if not activation_code or not card.check_activation_code(activation_code):
            messages.error(request, "Invalid activation code. Please enter the security PIN provided with your card package.")
            return redirect(redirect_target)

        # All checks passed: Activate & bind
        card.user = request.user
        card.profile = profile
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()

    # Dispatch Brevo notification email
    try:
        BrevoEmailService.send_card_activation_notification(request.user, card)
    except Exception as e:
        import logging
        logging.getLogger('stride.cards').error(f"Failed to dispatch card activation email: {e}")

    # Referral reward check: runs OUTSIDE the atomic block so the card save is committed
    # before we query referral state. Failure must never block the user's success response.
    try:
        from apps.accounts.services.referral_service import record_card_activation
        record_card_activation(card)
    except Exception as e:
        import logging
        logging.getLogger('stride.referrals').error(
            "record_card_activation failed for card %s: %s", card.card_code, e
        )

    request.session['just_activated_card'] = card.card_code
    messages.success(request, f"Success! Smart Card {card.card_code} is now activated and linked to your digital profile.")
    return redirect('dashboard:card_manage')


@login_required
def card_activation_success_view(request, card_code):
    """
    Dedicated post-activation success screen (/c/<card_code>/success/).
    Shows active confirmation, what happens on future taps, and clear next steps.
    """
    card = get_object_or_404(Card, card_code__iexact=card_code.strip(), user=request.user)
    profile = getattr(request.user, 'profile', None)
    return render(request, 'cards/card_activation_success.html', {
        'card': card,
        'profile': profile,
    })


@login_required
@require_POST
def card_report_lost_view(request, card_id):
    """Customer reports their physical smart card as lost."""
    card = get_object_or_404(Card, id=card_id, user=request.user)
    card.status = Card.STATUS_LOST
    card.save()

    # Dispatch security alert email
    try:
        BrevoEmailService.send_card_status_email(request.user, card, action='lost')
    except Exception as e:
        import logging
        logging.getLogger('stride.cards').error(f"Failed to dispatch lost card email: {e}")

    messages.warning(request, f"Smart Card {card.card_code} has been marked as LOST. It will no longer redirect to your profile.")
    return redirect('dashboard:card_manage')

