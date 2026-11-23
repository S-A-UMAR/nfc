import csv
import io
import re
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404, FileResponse, JsonResponse
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, Q, Min, Max
from django.core.paginator import Paginator
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from apps.cards.models import Card, CardEvent
from apps.orders.models import Order, ProductPackage
from apps.core.models import AdminAuditLog, BusinessInquiry
from apps.websites.models import Website
from apps.core.security import get_client_ip
from apps.core.permissions import (
    console_staff_required,
    manager_required,
    is_operations_manager,
    can_manage_pins,
)
from apps.cards.services.card_generator import (
    create_card_batch,
    generate_batch_reference,
    STRIDE_ALPHABET,
    STRIDE_CODE_REGEX,
    sanitize_csv_cell,
)
from apps.cards.services.qr_service import (
    generate_qr_png_bytes,
    generate_qr_svg_bytes,
    generate_batch_manufacturing_zip,
    get_canonical_card_url,
)
from apps.cards.services.packaging_service import (
    get_packaging_manifest,
    acknowledge_packaging_manifest,
    build_packaging_csv_content,
    generate_packaging_slips_pdf,
    regenerate_card_activation_pin,
    regenerate_batch_activation_pins,
)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONSOLE OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_overview_view(request):
    """STRIDE Console Executive & Operations Overview."""
    # Customers
    total_customers = User.objects.filter(is_staff=False).count()
    active_customers = User.objects.filter(is_staff=False, is_active=True).count()
    total_staff = User.objects.filter(is_staff=True).count()

    # Cards inventory counts
    card_counts = Card.objects.aggregate(
        total=Count('id'),
        unassigned=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED)),
        reserved=Count('id', filter=Q(status=Card.STATUS_RESERVED)),
        active=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        suspended=Count('id', filter=Q(status=Card.STATUS_SUSPENDED)),
        lost=Count('id', filter=Q(status=Card.STATUS_LOST)),
        replaced=Count('id', filter=Q(status=Card.STATUS_REPLACED)),
        warehouse_stock=Count('id', filter=Q(is_warehouse_stock=True)),
    )

    # Provisioning readiness
    provisioning_counts = Card.objects.aggregate(
        stage_generated=Count('id', filter=Q(provisioning_stage=Card.STAGE_GENERATED)),
        stage_encoded=Count('id', filter=Q(provisioning_stage=Card.STAGE_ENCODED)),
        stage_packaged=Count('id', filter=Q(provisioning_stage=Card.STAGE_PACKAGED)),
        stage_ready=Count('id', filter=Q(provisioning_stage=Card.STAGE_READY)),
    )

    # Orders
    order_counts = Order.objects.aggregate(
        total=Count('id'),
        paid=Count('id', filter=Q(payment_status=Order.PAYMENT_PAID)),
        pending=Count('id', filter=Q(payment_status=Order.PAYMENT_PENDING)),
        production=Count('id', filter=Q(order_status=Order.STATUS_PRODUCTION)),
        delivery=Count('id', filter=Q(order_status=Order.STATUS_DELIVERY)),
        completed=Count('id', filter=Q(order_status=Order.STATUS_COMPLETED)),
    )

    # Inquiries
    inquiry_counts = BusinessInquiry.objects.aggregate(
        total=Count('id'),
        new=Count('id', filter=Q(status=BusinessInquiry.STATUS_NEW)),
        contacted=Count('id', filter=Q(status=BusinessInquiry.STATUS_CONTACTED)),
    )

    # Websites
    website_counts = Website.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(status=Website.STATUS_PUBLISHED)),
        draft=Count('id', filter=Q(status=Website.STATUS_DRAFT)),
    )

    # Recent Audit Activity & Pending Fulfillment Orders
    recent_audit_logs = AdminAuditLog.objects.select_related('staff_user').order_by('-created_at')[:8]
    pending_orders = Order.objects.filter(
        payment_status=Order.PAYMENT_PAID
    ).exclude(
        order_status=Order.STATUS_COMPLETED
    ).select_related('user', 'package', 'card_assigned').order_by('-created_at')[:6]
    recent_card_events = CardEvent.objects.select_related('card', 'card__user').order_by('-created_at')[:6]

    # Explicit pairing metrics for top cards
    unpaired_stock = Card.objects.filter(status=Card.STATUS_UNASSIGNED, user__isnull=True).count()
    pending_activation = Card.objects.filter(
        Q(status=Card.STATUS_RESERVED) | Q(user__isnull=False, status=Card.STATUS_UNASSIGNED)
    ).count()

    return render(request, 'console/overview.html', {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_staff': total_staff,
        'card_counts': card_counts,
        'unpaired_stock': unpaired_stock,
        'pending_activation': pending_activation,
        'active_linked': card_counts.get('active', 0),
        'provisioning_counts': provisioning_counts,
        'order_counts': order_counts,
        'inquiry_counts': inquiry_counts,
        'website_counts': website_counts,
        'recent_audit_logs': recent_audit_logs,
        'pending_orders': pending_orders,
        'recent_card_events': recent_card_events,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. CARD INVENTORY & SEARCH
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_cards_list_view(request):
    """Filterable, searchable smart card hardware inventory."""
    qs = Card.objects.select_related('user', 'profile').order_by('-created_at')

    # Status filter
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all' and status_filter in dict(Card.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    # Pairing filter
    pairing_filter = request.GET.get('pairing', 'all')
    if pairing_filter == 'unpaired':
        qs = qs.filter(status=Card.STATUS_UNASSIGNED, user__isnull=True)
    elif pairing_filter == 'paired_pending':
        qs = qs.filter(Q(status=Card.STATUS_RESERVED) | Q(user__isnull=False, status=Card.STATUS_UNASSIGNED))
    elif pairing_filter == 'active':
        qs = qs.filter(status=Card.STATUS_ACTIVE)
    elif pairing_filter == 'inactive':
        qs = qs.filter(status__in=[Card.STATUS_SUSPENDED, Card.STATUS_LOST, Card.STATUS_REPLACED])

    # Material filter
    material_filter = request.GET.get('material', 'all')
    if material_filter != 'all' and material_filter in dict(Card.MATERIAL_CHOICES):
        qs = qs.filter(material=material_filter)

    # Provisioning stage filter
    stage_filter = request.GET.get('stage', 'all')
    if stage_filter != 'all' and stage_filter in dict(Card.PROVISIONING_STAGE_CHOICES):
        qs = qs.filter(provisioning_stage=stage_filter)

    # Hardware verification filter
    hardware_test_filter = request.GET.get('hardware_test', 'all').strip().lower()
    if hardware_test_filter != 'all' and hardware_test_filter in dict(Card.HARDWARE_TEST_CHOICES):
        qs = qs.filter(hardware_test_status=hardware_test_filter)

    # Warehouse stock filter
    warehouse_filter = request.GET.get('warehouse', 'all')
    if warehouse_filter == 'yes':
        qs = qs.filter(is_warehouse_stock=True)
    elif warehouse_filter == 'no':
        qs = qs.filter(is_warehouse_stock=False)

    # Batch reference filter
    batch_filter = request.GET.get('batch', '').strip()
    if batch_filter:
        qs = qs.filter(batch_reference__iexact=batch_filter)

    # Search query
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(card_code__icontains=q) |
            Q(batch_reference__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(profile__full_name__icontains=q)
        )

    # Aggregated counts for tab chips
    status_counts = Card.objects.aggregate(
        total=Count('id'),
        unassigned=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED)),
        reserved=Count('id', filter=Q(status=Card.STATUS_RESERVED)),
        active=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        suspended=Count('id', filter=Q(status=Card.STATUS_SUSPENDED)),
        lost=Count('id', filter=Q(status=Card.STATUS_LOST)),
        replaced=Count('id', filter=Q(status=Card.STATUS_REPLACED)),
    )

    pairing_counts = Card.objects.aggregate(
        total=Count('id'),
        unpaired=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED, user__isnull=True)),
        paired_pending=Count('id', filter=Q(status=Card.STATUS_RESERVED) | Q(user__isnull=False, status=Card.STATUS_UNASSIGNED)),
        active=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        inactive=Count('id', filter=Q(status__in=[Card.STATUS_SUSPENDED, Card.STATUS_LOST, Card.STATUS_REPLACED])),
    )

    # Available batches for quick dropdown filter
    recent_batches = (
        Card.objects.exclude(batch_reference='')
        .values_list('batch_reference', flat=True)
        .distinct()[:15]
    )

    paginator = Paginator(qs, 30)
    page_number = request.GET.get('page')
    cards_page = paginator.get_page(page_number)

    return render(request, 'console/cards_list.html', {
        'cards': cards_page,
        'search_query': q,
        'status_filter': status_filter,
        'pairing_filter': pairing_filter,
        'material_filter': material_filter,
        'stage_filter': stage_filter,
        'hardware_test_filter': hardware_test_filter,
        'warehouse_filter': warehouse_filter,
        'batch_filter': batch_filter,
        'status_counts': status_counts,
        'pairing_counts': pairing_counts,
        'status_choices': Card.STATUS_CHOICES,
        'material_choices': Card.MATERIAL_CHOICES,
        'stage_choices': Card.PROVISIONING_STAGE_CHOICES,
        'hardware_test_choices': Card.HARDWARE_TEST_CHOICES,
        'recent_batches': recent_batches,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 3. SECURE CARD GENERATION (CANONICAL ST-XXXXXXXX)
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_card_generate_view(request):
    """
    Generate new physical card records (single or bulk batch).
    Enforces canonical format: ST-XXXXXXXX (8 random alphanumeric characters).
    Enforces inventory defaults: UNASSIGNED, is_warehouse_stock=True.
    Hands off plaintext PINs to temporary one-time packaging manifest.
    """
    if request.method == 'POST':
        count_str = request.POST.get('count', '1').strip()
        material = request.POST.get('material', 'matte_black')
        batch_ref = request.POST.get('batch_reference', '').strip().upper()

        try:
            count = int(count_str)
        except ValueError:
            count = 1

        allowed_counts = (1, 5, 10, 25, 50, 100)
        if count not in allowed_counts:
            # Clamp to nearest valid or standard
            count = 1 if count < 1 else min(count, 100)

        if not batch_ref:
            batch_ref = generate_batch_reference()

        ip = get_client_ip(request)

        try:
            cards, token = create_card_batch(
                count=count,
                material=material,
                batch_reference=batch_ref,
                staff_user=request.user,
                ip_address=ip,
            )
            messages.success(
                request,
                f"Generated {len(cards)} new cards in batch {batch_ref}. "
                "Activation PINs are available in the one-time packaging manifest below. "
                "Download or print credentials now — plaintext PINs cannot be recovered once purged."
            )
            return redirect('console:card_packaging', token=token)
        except Exception as e:
            messages.error(request, f"Card generation failed: {e}")
            return redirect('console:card_generate')

    return render(request, 'console/card_generate.html', {
        'default_batch_ref': generate_batch_reference(),
        'material_choices': Card.MATERIAL_CHOICES,
        'supported_counts': [1, 5, 10, 25, 50, 100],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. ONE-TIME PACKAGING MANIFEST & REVEAL
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_card_packaging_view(request, token):
    """
    Controlled one-time packaging credential review view.
    Reads ephemeral manifest from cache.
    Provides options to print slips or download packaging CSV.
    """
    manifest = get_packaging_manifest(token)
    if not manifest:
        messages.warning(
            request,
            "Packaging manifest has expired or has already been acknowledged and purged from memory. "
            "Plaintext activation PINs are no longer recoverable. Use PIN Regeneration if a packaging slip was lost."
        )
        return redirect('console:cards_list')

    creator_email = manifest.get('staff_email')
    if creator_email and creator_email != request.user.email and not is_operations_manager(request.user):
        raise PermissionDenied("You do not have permission to access packaging credentials generated by another staff member.")

    return render(request, 'console/card_packaging.html', {
        'token': token,
        'manifest': manifest,
        'cards': manifest.get('cards', []),
        'can_download_csv': can_manage_pins(request.user),
    })


@console_staff_required
@manager_required
def console_packaging_csv_download(request, token):
    """
    Restricted one-time packaging CSV download containing Card ID and Activation PIN.
    Applies formula-injection protection and strict no-cache headers.
    """
    manifest = get_packaging_manifest(token)
    if not manifest:
        messages.error(request, "Manifest expired or unavailable.")
        return redirect('console:cards_list')

    creator_email = manifest.get('staff_email')
    if creator_email and creator_email != request.user.email and not is_operations_manager(request.user):
        raise PermissionDenied("You do not have permission to view or print packaging credentials generated by another staff member.")

    # Audit the packaging CSV download
    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_PACKAGING_MANIFEST_DOWNLOADED,
        staff_user=request.user,
        target_repr=f"Batch {manifest.get('batch_reference')}",
        target_model="Card",
        target_id=manifest.get('batch_reference', ''),
        details=f"Staff downloaded packaging CSV for {len(manifest.get('cards', []))} cards",
        ip_address=get_client_ip(request),
    )

    csv_data = build_packaging_csv_content(manifest)
    batch_ref = manifest.get('batch_reference', 'BATCH')
    filename = f"STRIDE_PACKAGING_{batch_ref}.csv"

    response = HttpResponse(csv_data, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@console_staff_required
def console_packaging_pdf_download(request, token):
    """
    High-quality print-ready A4 PDF download of all packaging slips in the manifest.
    Formatted 8 slips per page with cutting guides and confidential PIN styling.
    Strict no-cache headers and manager/creator authorization check.
    """
    manifest = get_packaging_manifest(token)
    if not manifest:
        messages.error(request, "Manifest expired or unavailable.")
        return redirect('console:cards_list')

    creator_email = manifest.get('staff_email')
    if creator_email and creator_email != request.user.email and not is_operations_manager(request.user):
        raise PermissionDenied("You do not have permission to view or print packaging credentials generated by another staff member.")

    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_PACKAGING_MANIFEST_DOWNLOADED,
        staff_user=request.user,
        target_repr=f"Batch {manifest.get('batch_reference')}",
        target_model="Card",
        target_id=manifest.get('batch_reference', ''),
        details=f"Staff downloaded packaging PDF for {len(manifest.get('cards', []))} cards",
        ip_address=get_client_ip(request),
    )

    pdf_buffer = generate_packaging_slips_pdf(manifest)
    batch_ref = manifest.get('batch_reference', 'BATCH')
    filename = f"STRIDE_SLIPS_{batch_ref}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@console_staff_required
def console_packaging_print_view(request, token):
    """
    Printable packaging slips view.
    Formatted specifically for thermal and packaging card inserts with @media print styling.
    """
    manifest = get_packaging_manifest(token)
    if not manifest:
        messages.error(request, "Manifest expired or unavailable.")
        return redirect('console:cards_list')

    creator_email = manifest.get('staff_email')
    if creator_email and creator_email != request.user.email and not is_operations_manager(request.user):
        raise PermissionDenied("You do not have permission to view or print packaging credentials generated by another staff member.")

    return render(request, 'console/packaging_slips_print.html', {
        'token': token,
        'manifest': manifest,
        'cards': manifest.get('cards', []),
    })


@console_staff_required
@require_POST
def console_packaging_acknowledge_view(request, token):
    """Staff acknowledges receipt and purges the plaintext PINs from memory."""
    manifest = get_packaging_manifest(token)
    if manifest:
        creator_email = manifest.get('staff_email')
        if creator_email and creator_email != request.user.email and not is_operations_manager(request.user):
            raise PermissionDenied("You do not have permission to acknowledge packaging credentials generated by another staff member.")
    acknowledge_packaging_manifest(token)
    messages.success(request, "Packaging credentials have been acknowledged and securely purged from temporary memory.")
    return redirect('console:cards_list')


# ─────────────────────────────────────────────────────────────────────────────
# 5. CARD DETAIL & PROVISIONING ACTIONS
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_card_detail_view(request, card_id):
    """Comprehensive Card Detail View in STRIDE Console."""
    card = get_object_or_404(
        Card.objects.select_related('user', 'profile', 'replacement_for', 'hardware_tested_by'),
        id=card_id
    )
    card_events = card.events.all()[:25]
    audit_trail = AdminAuditLog.objects.filter(target_model='Card', target_id=str(card.id)).order_by('-created_at')[:20]

    # Initial customers list for quick assignment (fallback when search query is empty)
    customers = User.objects.filter(is_active=True).order_by('email')[:30]
    # Unassigned cards for replacement
    unassigned_cards = Card.objects.filter(status=Card.STATUS_UNASSIGNED).exclude(id=card.id)[:50]

    # Active order if assigned to one
    linked_order = Order.objects.filter(card_assigned=card).first()
    batch_cards_count = Card.objects.filter(batch_reference=card.batch_reference).count() if card.batch_reference else 0

    return render(request, 'console/card_detail.html', {
        'card': card,
        'card_events': card_events,
        'audit_trail': audit_trail,
        'customers': customers,
        'unassigned_cards': unassigned_cards,
        'linked_order': linked_order,
        'can_regen_pin': can_manage_pins(request.user) and card.status != Card.STATUS_ACTIVE,
        'can_regenerate_pin': can_manage_pins(request.user) and card.status != Card.STATUS_ACTIVE,
        'canonical_url': card.get_canonical_production_url(),
        'staging_url': card.get_staging_test_url(),
        'canonical_nfc_url': card.get_canonical_production_url(),
        'batch_cards_count': batch_cards_count,
        'stage_choices': Card.PROVISIONING_STAGE_CHOICES,
        'hardware_test_choices': Card.HARDWARE_TEST_CHOICES,
    })


@console_staff_required
@require_GET
def console_card_qr_download_png(request, card_id):
    """Download single card QR code as high-contrast PNG."""
    card = get_object_or_404(Card, id=card_id)
    png_bytes = generate_qr_png_bytes(card.card_code, force_production=True)
    filename = f"QR_{card.card_code}.png"

    response = HttpResponse(png_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@console_staff_required
@require_GET
def console_card_qr_download_svg(request, card_id):
    """Download single card QR code as resolution-independent vector SVG for laser engraver."""
    card = get_object_or_404(Card, id=card_id)
    svg_bytes = generate_qr_svg_bytes(card.card_code, force_production=True)
    filename = f"QR_{card.card_code}.svg"

    response = HttpResponse(svg_bytes, content_type='image/svg+xml')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@console_staff_required
def console_card_batch_export_zip(request):
    """
    Download production manufacturing ZIP for a batch.
    Contains:
    - svg/<card_code>.svg
    - png/<card_code>.png
    - nfc_encoding_manifest.csv (Card_Code, NFC_URL, Material)
    NOTE: PINs are strictly excluded.
    """
    batch_ref = request.GET.get('batch', '').strip()
    if not batch_ref:
        messages.error(request, "Please specify a batch reference to export.")
        return redirect('console:cards_list')

    cards = Card.objects.filter(batch_reference=batch_ref)
    if not cards.exists():
        messages.error(request, f"No cards found matching batch reference '{batch_ref}'.")
        return redirect('console:cards_list')

    # Audit export
    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_CARD_BATCH_EXPORTED,
        staff_user=request.user,
        target_repr=f"Batch {batch_ref} ({cards.count()} cards)",
        target_model="Card",
        target_id=batch_ref,
        details=f"Exported manufacturing ZIP (SVGs, PNGs, NFC CSV) for {cards.count()} cards",
        ip_address=get_client_ip(request),
    )

    zip_buffer = generate_batch_manufacturing_zip(cards, batch_reference=batch_ref)
    filename = f"STRIDE_PROVISIONING_{batch_ref}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 6. EMERGENCY PIN REGENERATION (MANAGER ONLY)
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
@manager_required
@require_POST
def console_card_regenerate_pin_view(request, card_id):
    """
    Emergency activation PIN regeneration for unactivated cards.
    Requires reason and confirmation.
    Replaces hash atomically and provides a one-time reveal.
    """
    reason = request.POST.get('reason', '').strip()
    confirm = request.POST.get('confirm_regen', '')

    if confirm != 'yes':
        messages.error(request, "PIN regeneration requires explicit confirmation.")
        return redirect('console:card_detail', card_id=card_id)

    ip = get_client_ip(request)

    try:
        card, new_pin, token = regenerate_card_activation_pin(
            card_id=card_id,
            staff_user=request.user,
            reason=reason,
            ip_address=ip,
        )
        messages.success(
            request,
            f"Successfully regenerated activation PIN for card {card.card_code}. "
            "The previous PIN is invalidated. View or print the new packaging credential below."
        )
        return redirect('console:card_packaging', token=token)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('console:card_detail', card_id=card_id)


# ─────────────────────────────────────────────────────────────────────────────
# 7. PROVISIONING STAGE UPDATE
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
@require_POST
def console_card_update_stage_view(request, card_id):
    """Update card manufacturing / provisioning stage."""
    card = get_object_or_404(Card, id=card_id)
    new_stage = request.POST.get('provisioning_stage', '').strip()

    valid_stages = dict(Card.PROVISIONING_STAGE_CHOICES)
    if new_stage not in valid_stages:
        messages.error(request, "Invalid provisioning stage.")
        return redirect('console:card_detail', card_id=card.id)

    prev_stage = card.get_provisioning_stage_display()
    card.provisioning_stage = new_stage
    card.save(update_fields=['provisioning_stage'])

    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_CARD_STATUS if hasattr(AdminAuditLog, 'ACTION_CARD_STATUS') else AdminAuditLog.ACTION_CARD_CREATED,
        staff_user=request.user,
        target_repr=f"Card {card.card_code}",
        target_model="Card",
        target_id=str(card.id),
        previous_state=f"Stage: {prev_stage}",
        new_state=f"Stage: {card.get_provisioning_stage_display()}",
        details=f"Updated provisioning stage to {card.get_provisioning_stage_display()}",
        ip_address=get_client_ip(request),
    )

    messages.success(request, f"Card {card.card_code} updated to '{card.get_provisioning_stage_display()}'.")
    return redirect('console:card_detail', card_id=card.id)


# ─────────────────────────────────────────────────────────────────────────────
# 7b. HARDWARE VERIFICATION (PHYSICAL CHIP TESTING)
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
@require_POST
def console_card_hardware_test_view(request, card_id):
    """
    Record manual physical hardware verification result for a programmed NFC card.
    Staff physically taps/tests the programmed chip and records:
    - passed: Physical chip tested and verified working.
    - failed: Physical test failed (records failure reason, does NOT mark verified).
    - untested: Resets test status.
    """
    test_result = request.POST.get('test_result', '').strip().lower()
    notes = request.POST.get('notes', '').strip()

    valid_results = dict(Card.HARDWARE_TEST_CHOICES)
    if test_result not in valid_results:
        messages.error(request, f"Invalid hardware test result '{test_result}'.")
        return redirect('console:card_detail', card_id=card_id)

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_test_status = card.get_hardware_test_status_display()
        prev_stage = card.provisioning_stage

        card.hardware_test_status = test_result
        card.hardware_test_notes = notes

        if test_result == Card.HARDWARE_TEST_PASSED:
            card.hardware_tested_at = timezone.now()
            card.hardware_tested_by = request.user
            # If still in generated stage, advance to encoded stage since physical chip was verified
            if card.provisioning_stage == Card.STAGE_GENERATED:
                card.provisioning_stage = Card.STAGE_ENCODED
            msg_type = messages.SUCCESS
            msg_text = f"Hardware verification PASSED for card {card.card_code}. Recorded physical verification."
        elif test_result == Card.HARDWARE_TEST_FAILED:
            card.hardware_tested_at = timezone.now()
            card.hardware_tested_by = request.user
            # Crucial requirement: Does NOT mark verified, does NOT advance stage!
            msg_type = messages.WARNING
            msg_text = f"Hardware test recorded as FAILED for card {card.card_code}. Card is NOT verified. Reason: {notes or 'No reason provided'}."
        else:
            card.hardware_tested_at = None
            card.hardware_tested_by = None
            msg_type = messages.INFO
            msg_text = f"Hardware test status reset to Untested for card {card.card_code}."

        fields_to_update = ['hardware_test_status', 'hardware_tested_at', 'hardware_tested_by', 'hardware_test_notes']
        if card.provisioning_stage != prev_stage:
            fields_to_update.append('provisioning_stage')

        card.save(update_fields=fields_to_update)

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_HARDWARE_TESTED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=f"Test: {prev_test_status}",
            new_state=f"Test: {card.get_hardware_test_status_display()}",
            details=f"Staff {request.user.email} recorded hardware test '{card.get_hardware_test_status_display()}'. Notes: {notes or 'None'}",
            ip_address=get_client_ip(request),
        )

    if msg_type == messages.SUCCESS:
        messages.success(request, msg_text)
    elif msg_type == messages.WARNING:
        messages.warning(request, msg_text)
    else:
        messages.info(request, msg_text)

    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_batch_hardware_test_view(request, batch_reference):
    """
    Bulk hardware verification recording for an entire batch.
    Allows recording all cards in the batch as physically tested.
    """
    clean_batch = batch_reference.strip()
    test_result = request.POST.get('test_result', '').strip().lower()
    notes = request.POST.get('notes', '').strip()

    valid_results = dict(Card.HARDWARE_TEST_CHOICES)
    if test_result not in valid_results:
        messages.error(request, f"Invalid hardware test result '{test_result}'.")
        return redirect('console:batch_detail', batch_reference=clean_batch)

    if test_result == Card.HARDWARE_TEST_PASSED and not notes:
        messages.error(
            request,
            "Physical verification evidence notes (e.g. QA station, antenna sweep log, reader tap confirmation) are required before bulk recording hardware as passed."
        )
        return redirect('console:batch_detail', batch_reference=clean_batch)

    cards = Card.objects.filter(batch_reference=clean_batch)
    count = cards.count()
    if count == 0:
        messages.error(request, f"No cards found matching batch '{clean_batch}'.")
        return redirect('console:batches_list')

    with transaction.atomic():
        cards_to_update = list(cards.select_for_update())
        now = timezone.now() if test_result != Card.HARDWARE_TEST_UNTESTED else None
        tester = request.user if test_result != Card.HARDWARE_TEST_UNTESTED else None

        updated_count = 0
        for card in cards_to_update:
            card.hardware_test_status = test_result
            card.hardware_tested_at = now
            card.hardware_tested_by = tester
            if notes:
                card.hardware_test_notes = notes
            if test_result == Card.HARDWARE_TEST_PASSED and card.provisioning_stage == Card.STAGE_GENERATED:
                card.provisioning_stage = Card.STAGE_ENCODED
            card.save(update_fields=['hardware_test_status', 'hardware_tested_at', 'hardware_tested_by', 'hardware_test_notes', 'provisioning_stage'])
            updated_count += 1

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_HARDWARE_TESTED,
            staff_user=request.user,
            target_repr=f"Batch {clean_batch} ({updated_count} cards)",
            target_model="Card",
            target_id=clean_batch,
            previous_state="",
            new_state=f"Hardware Test: {valid_results[test_result]}",
            details=f"Staff recorded bulk hardware test '{valid_results[test_result]}' for {updated_count} cards in batch {clean_batch}. Notes: {notes or 'None'}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Recorded hardware verification '{valid_results[test_result]}' for all {updated_count} cards in batch {clean_batch}.")
    return redirect('console:batch_detail', batch_reference=clean_batch)


# ─────────────────────────────────────────────────────────────────────────────
# 7c. CUSTOMER SEARCH API (FOR ASSIGNMENT)
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
@require_GET
def console_customer_search_api(request):
    """
    Server-side search for customer assignment in Console.
    Searches by name and email.
    Returns JSON list of matching active customers with profile details and card count.
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': [], 'count': 0})

    users = (
        User.objects.filter(is_active=True)
        .filter(
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(profile__full_name__icontains=q)
        )
        .select_related('profile')
        .annotate(cards_count=Count('cards'))
        .order_by('email')[:15]
    )

    results = []
    for u in users:
        full_name = u.get_full_name() or (u.profile.full_name if hasattr(u, 'profile') and u.profile else '')
        display = full_name.strip() if full_name and full_name.strip() else u.email
        results.append({
            'id': u.id,
            'email': u.email,
            'name': display,
            'initial': (display[0] if display else 'U').upper(),
            'cards_count': u.cards_count,
            'phone': getattr(u, 'phone_number', '') or (u.profile.phone if hasattr(u, 'profile') and u.profile else ''),
        })

    return JsonResponse({'results': results, 'count': len(results)})


# ─────────────────────────────────────────────────────────────────────────────
# 8. CARD ASSIGNMENT & LIFECYCLE (STATUS_RESERVED ENFORCEMENT)
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
@require_POST
def console_card_assign_view(request, card_id):
    """
    Assign an unassigned card to a customer with explicit confirmation.
    IMPORTANT: Normal staff assignment sets card.status = STATUS_RESERVED,
    NOT STATUS_ACTIVE! The card activates only when the customer taps and enters PIN.
    """
    user_id = request.POST.get('user_id')
    confirm_assign = request.POST.get('confirm_assign')

    if not user_id:
        messages.error(request, "Please search and select a customer to assign.")
        return redirect('console:card_detail', card_id=card_id)

    # If confirm_assign is submitted (e.g. from web form), it must be explicitly checked
    if confirm_assign is not None and confirm_assign.strip().lower() not in ('yes', 'true', '1'):
        messages.error(request, "Assignment requires explicit confirmation. Please check the confirmation box.")
        return redirect('console:card_detail', card_id=card_id)

    customer = get_object_or_404(User, id=user_id)
    if not customer.is_active:
        messages.error(request, f"Customer account '{customer.email}' is inactive or suspended.")
        return redirect('console:card_detail', card_id=card_id)

    profile = getattr(customer, 'profile', None)

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)

        # Decommissioned check
        if card.status in (Card.STATUS_LOST, Card.STATUS_REPLACED):
            messages.error(request, f"Cannot assign decommissioned card '{card.card_code}' ({card.get_status_display()}).")
            return redirect('console:card_detail', card_id=card.id)

        # Duplicate assignment check
        if card.user == customer and card.status == Card.STATUS_RESERVED:
            messages.warning(request, f"Card '{card.card_code}' is already reserved for {customer.email}.")
            return redirect('console:card_detail', card_id=card.id)

        if card.status == Card.STATUS_ACTIVE:
            if card.user == customer:
                messages.warning(request, f"Card '{card.card_code}' is already active and linked to {customer.email}.")
            else:
                messages.error(request, f"Card '{card.card_code}' is already active for {card.user.email}. Use Reassign instead.")
            return redirect('console:card_detail', card_id=card.id)

        if card.status == Card.STATUS_RESERVED and card.user and card.user != customer:
            messages.error(request, f"Card '{card.card_code}' is already reserved for another customer ({card.user.email}).")
            return redirect('console:card_detail', card_id=card.id)

        prev_status = card.status
        prev_owner = card.user.email if card.user else "Unassigned"

        card.user = customer
        card.profile = profile
        card.status = Card.STATUS_RESERVED
        card.is_warehouse_stock = False
        card.activated_at = None  # STRICT: NOT active yet!
        card.save(update_fields=['user', 'profile', 'status', 'is_warehouse_stock', 'activated_at'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_ASSIGNED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=f"{prev_status} ({prev_owner})",
            new_state=f"RESERVED ({customer.email})",
            details=f"Reserved card for customer {customer.email}. Awaiting customer physical PIN activation.",
            ip_address=get_client_ip(request),
        )

    messages.success(
        request, 
        f"Card '{card.card_code}' successfully reserved for {customer.email}. "
        "The customer will activate the card upon delivery by tapping and entering their security PIN."
    )
    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_card_reassign_view(request, card_id):
    """Reassign an active card to another customer with confirmation."""
    confirm = request.POST.get('confirm_reassign')
    if confirm != 'yes':
        messages.error(request, "Reassignment confirmation required.")
        return redirect('console:card_detail', card_id=card_id)

    new_user_id = request.POST.get('new_user_id')
    new_customer = get_object_or_404(User, id=new_user_id)
    new_profile = getattr(new_customer, 'profile', None)

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_owner = card.user.email if card.user else "Unassigned"
        prev_status = card.status

        card.user = new_customer
        card.profile = new_profile
        card.status = Card.STATUS_RESERVED
        card.activated_at = None
        card.save(update_fields=['user', 'profile', 'status', 'activated_at'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_REASSIGNED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=f"Owner: {prev_owner}",
            new_state=f"Owner: {new_customer.email} (RESERVED)",
            details=f"Reassigned card from {prev_owner} to {new_customer.email}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{card.card_code}' reassigned to {new_customer.email} in RESERVED state.")
    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_card_suspend_view(request, card_id):
    """Temporarily suspend a card."""
    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_status = card.status
        card.status = Card.STATUS_SUSPENDED
        card.save(update_fields=['status'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_SUSPENDED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=prev_status,
            new_state=Card.STATUS_SUSPENDED,
            details=f"Suspended card by staff {request.user.email}",
            ip_address=get_client_ip(request),
        )

    messages.warning(request, f"Card '{card.card_code}' is now suspended.")
    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_card_restore_view(request, card_id):
    """Restore a suspended card."""
    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        if card.status != Card.STATUS_SUSPENDED:
            messages.error(request, "Only suspended cards can be restored.")
            return redirect('console:card_detail', card_id=card.id)

        card.status = Card.STATUS_ACTIVE if card.user else Card.STATUS_UNASSIGNED
        card.save(update_fields=['status'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_RESTORED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=Card.STATUS_SUSPENDED,
            new_state=card.status,
            details=f"Restored card to {card.status}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{card.card_code}' restored to {card.status}.")
    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_card_mark_lost_view(request, card_id):
    """Permanently mark card as lost."""
    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_status = card.status
        card.status = Card.STATUS_LOST
        card.save(update_fields=['status'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_MARKED_LOST,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=prev_status,
            new_state=Card.STATUS_LOST,
            details=f"Card marked lost by staff {request.user.email}",
            ip_address=get_client_ip(request),
        )

    messages.error(request, f"Card '{card.card_code}' marked LOST.")
    return redirect('console:card_detail', card_id=card.id)


@console_staff_required
@require_POST
def console_card_replace_view(request, card_id):
    """Issue a replacement card for a lost or damaged card."""
    new_card_id = request.POST.get('new_card_id')
    if not new_card_id:
        messages.error(request, "Please select an unassigned card to use as a replacement.")
        return redirect('console:card_detail', card_id=card_id)

    with transaction.atomic():
        old_card = Card.objects.select_for_update().get(id=card_id)
        new_card = Card.objects.select_for_update().get(id=new_card_id, status=Card.STATUS_UNASSIGNED)

        target_user = old_card.user
        target_profile = old_card.profile

        # Retire old card
        old_card.status = Card.STATUS_REPLACED
        old_card.save(update_fields=['status'])

        # Bind new card as RESERVED for customer
        new_card.user = target_user
        new_card.profile = target_profile
        new_card.replacement_for = old_card
        new_card.status = Card.STATUS_RESERVED
        new_card.is_warehouse_stock = False
        new_card.save(update_fields=['user', 'profile', 'replacement_for', 'status', 'is_warehouse_stock'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_REPLACED,
            staff_user=request.user,
            target_repr=f"Card {old_card.card_code} → {new_card.card_code}",
            target_model="Card",
            target_id=str(new_card.id),
            previous_state=f"Old Card {old_card.card_code} REPLACED",
            new_state=f"New Card {new_card.card_code} RESERVED for {target_user.email if target_user else 'None'}",
            details=f"Replaced card {old_card.card_code} with {new_card.card_code}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Replacement card '{new_card.card_code}' reserved for customer. Previous card '{old_card.card_code}' marked REPLACED.")
    return redirect('console:card_detail', card_id=new_card.id)


# ─────────────────────────────────────────────────────────────────────────────
# 8. PRODUCTION BATCHES COMMAND HUB
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_batches_list_view(request):
    """
    Centralized production batches list with live hardware counts, stages, and manifests.
    """
    material_filter = request.GET.get('material', 'all').strip()
    stage_filter = request.GET.get('stage', 'all').strip()
    search_q = request.GET.get('q', '').strip()

    base_qs = Card.objects.exclude(batch_reference='')

    if search_q:
        base_qs = base_qs.filter(batch_reference__icontains=search_q)

    if material_filter != 'all' and material_filter in dict(Card.MATERIAL_CHOICES):
        base_qs = base_qs.filter(material=material_filter)

    if stage_filter != 'all' and stage_filter in dict(Card.PROVISIONING_STAGE_CHOICES):
        base_qs = base_qs.filter(provisioning_stage=stage_filter)

    # Aggregated batch metrics
    batch_rows = base_qs.values('batch_reference').annotate(
        total_cards=Count('id'),
        unpaired_count=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED, user__isnull=True)),
        paired_pending_count=Count('id', filter=Q(status=Card.STATUS_RESERVED) | Q(user__isnull=False, status=Card.STATUS_UNASSIGNED)),
        active_count=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        stage_generated=Count('id', filter=Q(provisioning_stage=Card.STAGE_GENERATED)),
        stage_encoded=Count('id', filter=Q(provisioning_stage=Card.STAGE_ENCODED)),
        stage_packaged=Count('id', filter=Q(provisioning_stage=Card.STAGE_PACKAGED)),
        stage_ready=Count('id', filter=Q(provisioning_stage=Card.STAGE_READY)),
        verified_count=Count('id', filter=Q(hardware_test_status=Card.HARDWARE_TEST_PASSED)),
        failed_count=Count('id', filter=Q(hardware_test_status=Card.HARDWARE_TEST_FAILED)),
        created_at=Min('created_at'),
    ).order_by('-created_at')

    # Enrich each batch with dominant material, display stage, and progress percentage
    enriched_batches = []
    for b in batch_rows:
        ref = b['batch_reference']
        materials = list(Card.objects.filter(batch_reference=ref).values_list('material', flat=True).distinct())
        material_labels = [dict(Card.MATERIAL_CHOICES).get(m, m) for m in materials]
        
        total = b['total_cards']
        ready_c = b['stage_ready']
        packaged_c = b['stage_packaged']
        encoded_c = b['stage_encoded']

        if ready_c == total and total > 0:
            stage_slug = 'ready'
            progress_pct = 100
        elif (packaged_c + ready_c) == total and total > 0:
            stage_slug = 'packaged'
            progress_pct = 75
        elif (encoded_c + packaged_c + ready_c) == total and total > 0:
            stage_slug = 'encoded'
            progress_pct = 50
        else:
            stage_slug = 'generated'
            progress_pct = 25

        enriched_batches.append({
            'batch_reference': ref,
            'total_cards': total,
            'unpaired_count': b['unpaired_count'],
            'paired_pending_count': b['paired_pending_count'],
            'active_count': b['active_count'],
            'verified_count': b['verified_count'],
            'failed_count': b['failed_count'],
            'materials': ", ".join(material_labels) or "Standard",
            'stage': stage_slug,
            'stage_display': dict(Card.PROVISIONING_STAGE_CHOICES).get(stage_slug, stage_slug.capitalize()),
            'progress_pct': progress_pct,
            'created_at': b['created_at'],
        })

    paginator = Paginator(enriched_batches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'console/batches_list.html', {
        'batches': page_obj,
        'search_query': search_q,
        'material_filter': material_filter,
        'stage_filter': stage_filter,
        'material_choices': Card.MATERIAL_CHOICES,
        'stage_choices': Card.PROVISIONING_STAGE_CHOICES,
        'total_batches_count': len(enriched_batches),
    })


@console_staff_required
def console_batch_detail_view(request, batch_reference):
    """
    Dedicated batch command center:
    - 4-step provisioning journey tracker
    - Bulk stage advancement
    - Bulk QR & NFC manufacturing ZIP download
    - Cards in batch with pairing status
    - Manager-only emergency bulk PIN regeneration
    """
    clean_batch = batch_reference.strip()
    cards_qs = Card.objects.filter(batch_reference=clean_batch).select_related('user', 'profile').order_by('card_code')
    total_cards = cards_qs.count()

    if total_cards == 0:
        messages.error(request, f"No cards found matching batch reference '{clean_batch}'.")
        return redirect('console:batches_list')

    unpaired_count = cards_qs.filter(status=Card.STATUS_UNASSIGNED, user__isnull=True).count()
    paired_pending_count = cards_qs.filter(
        Q(status=Card.STATUS_RESERVED) | Q(user__isnull=False, status=Card.STATUS_UNASSIGNED)
    ).count()
    active_count = cards_qs.filter(status=Card.STATUS_ACTIVE).count()
    decommissioned_count = cards_qs.filter(status__in=[Card.STATUS_LOST, Card.STATUS_REPLACED, Card.STATUS_SUSPENDED]).count()

    stage_counts = {
        'generated': cards_qs.filter(provisioning_stage=Card.STAGE_GENERATED).count(),
        'encoded': cards_qs.filter(provisioning_stage=Card.STAGE_ENCODED).count(),
        'packaged': cards_qs.filter(provisioning_stage=Card.STAGE_PACKAGED).count(),
        'ready': cards_qs.filter(provisioning_stage=Card.STAGE_READY).count(),
    }

    hardware_counts = {
        'verified': cards_qs.filter(hardware_test_status=Card.HARDWARE_TEST_PASSED).count(),
        'failed': cards_qs.filter(hardware_test_status=Card.HARDWARE_TEST_FAILED).count(),
        'untested': cards_qs.filter(hardware_test_status=Card.HARDWARE_TEST_UNTESTED).count(),
    }

    active_token = cache.get(f"batch_active_packaging_token:{clean_batch}")
    active_manifest = get_packaging_manifest(active_token) if active_token else None

    if stage_counts['ready'] == total_cards:
        current_stage = 'ready'
        next_stage = None
        current_step_num = 4
    elif (stage_counts['packaged'] + stage_counts['ready']) == total_cards:
        current_stage = 'packaged'
        next_stage = 'ready'
        current_step_num = 3
    elif (stage_counts['encoded'] + stage_counts['packaged'] + stage_counts['ready']) == total_cards:
        current_stage = 'encoded'
        next_stage = 'packaged'
        current_step_num = 2
    else:
        current_stage = 'generated'
        next_stage = 'encoded'
        current_step_num = 1

    materials = list(cards_qs.values_list('material', flat=True).distinct())
    material_labels = [dict(Card.MATERIAL_CHOICES).get(m, m) for m in materials]

    first_card = cards_qs.first()
    batch_created_at = first_card.created_at if first_card else None

    audit_logs = AdminAuditLog.objects.filter(
        target_model='Card',
        target_id=clean_batch
    ).select_related('staff_user').order_by('-created_at')[:15]

    can_regen = (
        is_operations_manager(request.user) and
        active_count == 0 and
        decommissioned_count == 0
    )

    return render(request, 'console/batch_detail.html', {
        'batch_reference': clean_batch,
        'cards': cards_qs,
        'total_cards': total_cards,
        'unpaired_count': unpaired_count,
        'paired_pending_count': paired_pending_count,
        'active_count': active_count,
        'stage_counts': stage_counts,
        'hardware_counts': hardware_counts,
        'verified_count': hardware_counts['verified'],
        'failed_test_count': hardware_counts['failed'],
        'untested_count': hardware_counts['untested'],
        'active_token': active_token,
        'active_manifest': active_manifest,
        'manifest_active': bool(active_token and active_manifest),
        'can_download_csv': can_manage_pins(request.user),
        'hardware_test_choices': Card.HARDWARE_TEST_CHOICES,
        'materials_display': ", ".join(material_labels),
        'created_at': batch_created_at,
        'current_stage': current_stage,
        'current_stage_display': dict(Card.PROVISIONING_STAGE_CHOICES).get(current_stage, current_stage.capitalize()),
        'current_step_num': current_step_num,
        'next_stage': next_stage,
        'next_stage_display': dict(Card.PROVISIONING_STAGE_CHOICES).get(next_stage, next_stage.capitalize()) if next_stage else None,
        'stage_choices': Card.PROVISIONING_STAGE_CHOICES,
        'can_regen_pins': can_regen,
        'audit_logs': audit_logs,
    })


@console_staff_required
@require_POST
def console_batch_update_stage_view(request, batch_reference):
    """
    Advance or update provisioning stage for an entire batch atomically.
    """
    clean_batch = batch_reference.strip()
    new_stage = request.POST.get('stage', '').strip()

    valid_stages = dict(Card.PROVISIONING_STAGE_CHOICES)
    if new_stage not in valid_stages:
        messages.error(request, f"Invalid provisioning stage '{new_stage}'.")
        return redirect('console:batch_detail', batch_reference=clean_batch)

    cards = Card.objects.filter(batch_reference=clean_batch)
    count = cards.count()
    if count == 0:
        messages.error(request, f"No cards found matching batch '{clean_batch}'.")
        return redirect('console:batches_list')

    with transaction.atomic():
        cards.update(provisioning_stage=new_stage)

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_BULK_CREATED,
            staff_user=request.user,
            target_repr=f"Batch {clean_batch} ({count} cards)",
            target_model="Card",
            target_id=clean_batch,
            new_state=new_stage,
            details=f"Staff updated provisioning stage of all {count} cards in batch {clean_batch} to '{valid_stages[new_stage]}'",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"All {count} cards in batch {clean_batch} advanced to '{valid_stages[new_stage]}'.")
    return redirect('console:batch_detail', batch_reference=clean_batch)


@console_staff_required
@manager_required
@require_POST
def console_batch_regenerate_pins_view(request, batch_reference):
    """
    Emergency bulk PIN regeneration for unactivated batch.
    Requires manager role and minimum 5-character reason.
    """
    clean_batch = batch_reference.strip()
    reason = request.POST.get('reason', '').strip()

    if not reason or len(reason) < 5:
        messages.error(request, "A valid reason (minimum 5 characters) is required for emergency bulk PIN regeneration.")
        return redirect('console:batch_detail', batch_reference=clean_batch)

    ip = get_client_ip(request)

    try:
        updated_cards, token = regenerate_batch_activation_pins(
            batch_reference=clean_batch,
            staff_user=request.user,
            reason=reason,
            ip_address=ip,
        )
        messages.success(
            request,
            f"Successfully regenerated activation PINs for {len(updated_cards)} cards in batch {clean_batch}. "
            "Download or print the replacement packaging slips immediately."
        )
        return redirect('console:card_packaging', token=token)
    except ValueError as e:
        messages.error(request, f"Emergency PIN regeneration rejected: {e}")
        return redirect('console:batch_detail', batch_reference=clean_batch)
    except Exception as e:
        messages.error(request, f"PIN regeneration failed: {e}")
        return redirect('console:batch_detail', batch_reference=clean_batch)


# ─────────────────────────────────────────────────────────────────────────────
# 9. ORDERS & FULFILLMENT
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_orders_list_view(request):
    """Filterable orders list."""
    qs = Order.objects.select_related('user', 'package', 'card_assigned').order_by('-created_at')

    payment_filter = request.GET.get('payment', 'all')
    if payment_filter != 'all':
        qs = qs.filter(payment_status=payment_filter)

    order_filter = request.GET.get('status', 'all')
    if order_filter != 'all':
        qs = qs.filter(order_status=order_filter)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(order_number__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(shipping_name__icontains=q) |
            Q(shipping_tracking_number__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    orders_page = paginator.get_page(page_number)

    return render(request, 'console/orders_list.html', {
        'orders': orders_page,
        'search_query': q,
        'payment_filter': payment_filter,
        'order_filter': order_filter,
        'payment_choices': Order.PAYMENT_STATUS_CHOICES,
        'order_status_choices': Order.ORDER_STATUS_CHOICES,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })


@console_staff_required
def console_order_detail_view(request, order_number):
    """Full order detail view with fulfillment controls."""
    order = get_object_or_404(
        Order.objects.select_related('user', 'package', 'card_assigned'),
        order_number=order_number,
    )
    requirement = getattr(order, 'requirement', None)
    payments = order.payments.all().order_by('-created_at') if hasattr(order, 'payments') else []

    # Unassigned cards available for assignment
    unassigned_cards = Card.objects.filter(status=Card.STATUS_UNASSIGNED).order_by('card_code')[:100]

    timeline_keys = [step[0] for step in Order.TIMELINE_STEPS]
    try:
        current_step_idx = timeline_keys.index(order.order_status)
    except ValueError:
        current_step_idx = 0

    return render(request, 'console/order_detail.html', {
        'order': order,
        'requirement': requirement,
        'payments': payments,
        'unassigned_cards': unassigned_cards,
        'timeline_steps': Order.TIMELINE_STEPS,
        'current_step_idx': current_step_idx,
        'order_status_choices': Order.ORDER_STATUS_CHOICES,
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
    })


@console_staff_required
@require_POST
def console_order_update_status_view(request, order_number):
    """Update order fulfillment status, payment, carrier tracking, or card allocation."""
    new_order_status = request.POST.get('order_status', '').strip()
    new_payment_status = request.POST.get('payment_status', '').strip()
    shipping_carrier = request.POST.get('shipping_carrier', '').strip()
    shipping_tracking = request.POST.get('shipping_tracking_number', '').strip()
    assign_card_id = request.POST.get('assign_card_id', '').strip()

    valid_order_statuses = [c[0] for c in Order.ORDER_STATUS_CHOICES]
    valid_payment_statuses = [c[0] for c in Order.PAYMENT_STATUS_CHOICES]

    changed = []

    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), order_number=order_number)

        if new_order_status and new_order_status != order.order_status:
            if new_order_status not in valid_order_statuses:
                messages.error(request, "Invalid order status.")
                return redirect('console:order_detail', order_number=order.order_number)
            old_s = order.get_order_status_display()
            order.order_status = new_order_status
            changed.append(f"Status: {old_s} → {order.get_order_status_display()}")

        if new_payment_status and new_payment_status != order.payment_status:
            if new_payment_status not in valid_payment_statuses:
                messages.error(request, "Invalid payment status.")
                return redirect('console:order_detail', order_number=order.order_number)
            old_p = order.get_payment_status_display()
            order.payment_status = new_payment_status
            changed.append(f"Payment: {old_p} → {order.get_payment_status_display()}")

        if shipping_carrier != order.shipping_carrier:
            order.shipping_carrier = shipping_carrier
            changed.append(f"Carrier: {shipping_carrier}")

        if shipping_tracking != order.shipping_tracking_number:
            order.shipping_tracking_number = shipping_tracking
            changed.append(f"Tracking: {shipping_tracking}")

        if assign_card_id:
            try:
                card = Card.objects.select_for_update().get(id=assign_card_id, status=Card.STATUS_UNASSIGNED)

                # Release old reserved card if any
                if order.card_assigned and order.card_assigned != card:
                    old_card = Card.objects.select_for_update().filter(id=order.card_assigned_id).first()
                    if old_card and old_card.status == Card.STATUS_RESERVED:
                        old_card.status = Card.STATUS_UNASSIGNED
                        old_card.user = None
                        old_card.is_warehouse_stock = True
                        old_card.save(update_fields=['status', 'user', 'is_warehouse_stock'])

                card.status = Card.STATUS_RESERVED
                card.is_warehouse_stock = False
                if order.user:
                    card.user = order.user
                card.save(update_fields=['status', 'user', 'is_warehouse_stock'])

                order.card_assigned = card
                changed.append(f"Card reserved: {card.card_code}")
            except Card.DoesNotExist:
                messages.error(request, "Card not found or no longer unassigned.")
                return redirect('console:order_detail', order_number=order.order_number)

        if changed:
            order.save()
            AdminAuditLog.log(
                action=AdminAuditLog.ACTION_ORDER_STATUS,
                staff_user=request.user,
                target_repr=f"Order #{order.order_number}",
                details="; ".join(changed),
                ip_address=get_client_ip(request),
            )
            messages.success(request, f"Order #{order.order_number} updated: {'; '.join(changed)}")
        else:
            messages.info(request, "No changes were made.")

    return redirect('console:order_detail', order_number=order.order_number)


# ─────────────────────────────────────────────────────────────────────────────
# 10. CUSTOMERS DIRECTORY
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_customers_list_view(request):
    """Customer accounts list."""
    qs = User.objects.filter(is_staff=False).select_related('profile').prefetch_related('cards').order_by('-date_joined')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(profile__full_name__icontains=q) |
            Q(profile__slug__icontains=q)
        )

    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'disabled':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    customers_page = paginator.get_page(page_number)

    return render(request, 'console/customers_list.html', {
        'customers': customers_page,
        'search_query': q,
        'status_filter': status_filter,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })


@console_staff_required
def console_customer_detail_view(request, user_id):
    """Detailed Customer inspection."""
    customer = get_object_or_404(User.objects.prefetch_related('cards', 'orders'), id=user_id)
    profile = getattr(customer, 'profile', None)
    customer_cards = customer.cards.all().order_by('-created_at')
    customer_orders = customer.orders.all().select_related('package', 'card_assigned').order_by('-created_at')
    audit_trail = AdminAuditLog.objects.filter(target_model='User', target_id=str(customer.id)).order_by('-created_at')[:20]

    return render(request, 'console/customer_detail.html', {
        'customer': customer,
        'profile': profile,
        'cards': customer_cards,
        'orders': customer_orders,
        'audit_trail': audit_trail,
    })


@console_staff_required
@require_POST
def console_customer_toggle_status_view(request, user_id):
    """Lock / unlock customer account."""
    customer = get_object_or_404(User, id=user_id)
    if customer.is_staff:
        messages.error(request, "Staff accounts cannot be modified here.")
        return redirect('console:customer_detail', user_id=customer.id)

    with transaction.atomic():
        customer = User.objects.select_for_update().get(id=user_id)
        prev_state = "Active" if customer.is_active else "Disabled"
        customer.is_active = not customer.is_active
        new_state = "Active" if customer.is_active else "Disabled"
        customer.save(update_fields=['is_active'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CUSTOMER_STATUS,
            staff_user=request.user,
            target_repr=f"Customer {customer.email}",
            target_model="User",
            target_id=str(customer.id),
            previous_state=prev_state,
            new_state=new_state,
            details=f"Account status toggled to {new_state}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Customer account {customer.email} is now {new_state}.")
    return redirect('console:customer_detail', user_id=customer.id)


# ─────────────────────────────────────────────────────────────────────────────
# 11. INQUIRIES CRM
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_inquiries_list_view(request):
    """Business inquiries pipeline list."""
    qs = BusinessInquiry.objects.select_related('assigned_staff').order_by('-created_at')

    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    inquiries_page = paginator.get_page(page_number)

    return render(request, 'console/inquiries_list.html', {
        'inquiries': inquiries_page,
        'status_filter': status_filter,
        'status_choices': BusinessInquiry.STATUS_CHOICES,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })


@console_staff_required
def console_inquiry_detail_view(request, inquiry_id):
    """Inquiry detail view."""
    inquiry = get_object_or_404(BusinessInquiry.objects.select_related('assigned_staff'), id=inquiry_id)
    staff_users = User.objects.filter(is_staff=True).order_by('first_name')

    return render(request, 'console/inquiry_detail.html', {
        'inquiry': inquiry,
        'staff_users': staff_users,
        'status_choices': BusinessInquiry.STATUS_CHOICES,
    })


@console_staff_required
@require_POST
def console_inquiry_update_status_view(request, inquiry_id):
    """Update lead status or assignment."""
    inquiry = get_object_or_404(BusinessInquiry, id=inquiry_id)
    new_status = request.POST.get('status')
    admin_notes = request.POST.get('admin_notes', '')

    if new_status in dict(BusinessInquiry.STATUS_CHOICES):
        inquiry.status = new_status
    inquiry.admin_notes = admin_notes
    inquiry.save(update_fields=['status', 'admin_notes', 'updated_at'])

    messages.success(request, "Inquiry updated successfully.")
    return redirect('console:inquiry_detail', inquiry_id=inquiry.id)


# ─────────────────────────────────────────────────────────────────────────────
# 12. WEBSITES
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_websites_list_view(request):
    """Customer website management."""
    qs = Website.objects.select_related('user').order_by('-created_at')
    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    websites_page = paginator.get_page(page_number)

    return render(request, 'console/websites_list.html', {
        'websites': websites_page,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })


@console_staff_required
@require_POST
def console_website_toggle_publish_view(request, website_id):
    """Publish / unpublish custom customer website."""
    website = get_object_or_404(Website, id=website_id)
    if website.status == Website.STATUS_PUBLISHED:
        website.status = Website.STATUS_UNPUBLISHED
    else:
        website.status = Website.STATUS_PUBLISHED
    website.save(update_fields=['status'])

    state_str = "Published" if website.status == Website.STATUS_PUBLISHED else "Unpublished (Draft)"
    messages.success(request, f"Website '{website.title}' is now {state_str}.")
    return redirect('console:websites_list')


# ─────────────────────────────────────────────────────────────────────────────
# 13. AUDIT LOGS
# ─────────────────────────────────────────────────────────────────────────────
@console_staff_required
def console_audit_logs_view(request):
    """Immutable audit logs review."""
    qs = AdminAuditLog.objects.select_related('staff_user').order_by('-created_at')

    action_filter = request.GET.get('action', 'all')
    if action_filter != 'all':
        qs = qs.filter(action=action_filter)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(target_repr__icontains=q) |
            Q(details__icontains=q) |
            Q(staff_user__email__icontains=q)
        )

    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page')
    logs_page = paginator.get_page(page_number)

    return render(request, 'console/audit_logs.html', {
        'logs': logs_page,
        'action_filter': action_filter,
        'action_choices': AdminAuditLog.ACTION_CHOICES,
        'search_query': q,
        'total_count': paginator.count,
        'can_export_zip': is_operations_manager(request.user),
    })
