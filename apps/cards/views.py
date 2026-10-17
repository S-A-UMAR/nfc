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
    if not is_owner and card.profile and request.COOKIES.get(f'uzyra_owner_{card.profile.slug}') == '1':
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
            response.set_cookie('uzyra_tap', '1', max_age=30, samesite='Lax')
            if is_owner:
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

    return render(request, 'dashboard/card_manage.html', {
        'profile': profile,
        'cards': cards,
        'primary_card': primary_card,
    })


from django.db import transaction
from apps.core.security import check_rate_limit, get_client_ip
from apps.core.services.email_service import BrevoEmailService

@login_required
@require_POST
def card_activate_view(request):
    """
    Customer activates or links a physical card to their profile.
    Security protections:
    1. Rate-limiting against brute force code guessing.
    2. Atomic transaction with select_for_update() to eliminate race conditions.
    3. Proof of physical ownership: secret activation PIN check.
    4. Status guards: Active, Suspended, Replaced, Lost cards rejected.
    5. Reassignment guards: Cannot reassign card belonging to another user.
    """
    ip = get_client_ip(request)
    user_id = request.user.id

    # Rate limiting: max 5 failed activation attempts per user/IP per 10 minutes
    allowed, remaining, retry_after = check_rate_limit(f"card_act:{user_id}", limit=5, window_seconds=600)
    if not allowed:
        messages.error(request, f"Too many failed card activation attempts. Throttled for {retry_after} seconds.")
        return redirect('dashboard:card_manage')

    card_code = request.POST.get('card_code', '').strip().upper()
    activation_code = request.POST.get('activation_code', '').strip().upper()
    profile = request.user.profile

    if not card_code:
        messages.error(request, "Please enter the Card ID code.")
        return redirect('dashboard:card_manage')

    with transaction.atomic():
        try:
            card = Card.objects.select_for_update().get(card_code__iexact=card_code)
        except Card.DoesNotExist:
            messages.error(request, f"Card '{card_code}' was not found. Please check the code printed on the physical card.")
            return redirect('dashboard:card_manage')

        # Guard: Already active
        if card.status == Card.STATUS_ACTIVE:
            messages.error(request, f"Card '{card_code}' is already active and in use.")
            return redirect('dashboard:card_manage')

        # Guard: Suspended
        if card.status == Card.STATUS_SUSPENDED:
            messages.error(request, f"Card '{card_code}' is suspended. Suspended cards cannot be activated.")
            return redirect('dashboard:card_manage')

        # Guard: Replaced
        if card.status == Card.STATUS_REPLACED:
            messages.error(request, f"Card '{card_code}' has been replaced and cannot be reactivated.")
            return redirect('dashboard:card_manage')

        # Guard: Reported Lost
        if card.status == Card.STATUS_LOST:
            messages.error(request, f"Card '{card_code}' has been reported lost and cannot be activated.")
            return redirect('dashboard:card_manage')

        # Guard: Assigned to another user
        if card.user and card.user != request.user:
            messages.error(request, f"Card '{card_code}' is already assigned to another account.")
            return redirect('dashboard:card_manage')

        # Guard: Activation PIN verification
        if card.activation_code_hash:
            if not activation_code or not card.check_activation_code(activation_code):
                messages.error(request, "Invalid activation code. Please enter the security PIN provided with your card package.")
                return redirect('dashboard:card_manage')

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
        logging.getLogger('uzyra.cards').error(f"Failed to dispatch card activation email: {e}")

    messages.success(request, f"Success! Smart Card {card.card_code} is now activated and linked to your digital profile.")
    return redirect('dashboard:card_manage')


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
        logging.getLogger('uzyra.cards').error(f"Failed to dispatch lost card email: {e}")

    messages.warning(request, f"Smart Card {card.card_code} has been marked as LOST. It will no longer redirect to your profile.")
    return redirect('dashboard:card_manage')

