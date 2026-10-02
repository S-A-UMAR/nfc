import re
from functools import wraps
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cards.models import Card, CardEvent
from apps.profiles.models import Profile
from apps.websites.models import Website
from apps.orders.models import Order
from apps.analytics.models import AnalyticsEvent
from .models import AdminAuditLog
from apps.core.security import get_client_ip

User = get_user_model()


def staff_required(view_func):
    """
    Decorator for views that checks that the user is authenticated and is a staff member.
    Raises PermissionDenied (403) for non-staff authenticated users.
    Redirects unauthenticated users to login with ?next=.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.urls import reverse
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not request.user.is_staff:
            raise PermissionDenied("Staff credentials required to access internal operations.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# ─────────────────────────────────────────────────────────────────────────────
# 1. OPERATIONS OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_overview_view(request):
    """Internal admin overview dashboard with real database metrics."""
    # Customers
    total_customers = User.objects.filter(is_staff=False).count()
    active_customers = User.objects.filter(is_staff=False, is_active=True).count()
    total_staff = User.objects.filter(is_staff=True).count()

    # Cards
    card_counts = Card.objects.aggregate(
        total=Count('id'),
        unassigned=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED)),
        reserved=Count('id', filter=Q(status=Card.STATUS_RESERVED)),
        active=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        suspended=Count('id', filter=Q(status=Card.STATUS_SUSPENDED)),
        lost=Count('id', filter=Q(status=Card.STATUS_LOST)),
        replaced=Count('id', filter=Q(status=Card.STATUS_REPLACED)),
    )

    # Websites
    website_counts = Website.objects.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(status=Website.STATUS_PUBLISHED)),
        draft=Count('id', filter=Q(status=Website.STATUS_DRAFT)),
        unpublished=Count('id', filter=Q(status=Website.STATUS_UNPUBLISHED)),
    )

    # Orders
    order_counts = Order.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(payment_status=Order.PAYMENT_PENDING)),
        paid=Count('id', filter=Q(payment_status=Order.PAYMENT_PAID)),
        completed=Count('id', filter=Q(order_status=Order.STATUS_COMPLETED)),
    )

    # Recent Audit Logs
    recent_audit_logs = AdminAuditLog.objects.select_related('staff_user').order_by('-created_at')[:10]
    recent_card_events = CardEvent.objects.select_related('card').order_by('-created_at')[:10]

    return render(request, 'operations/overview.html', {
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_staff': total_staff,
        'card_counts': card_counts,
        'website_counts': website_counts,
        'order_counts': order_counts,
        'recent_audit_logs': recent_audit_logs,
        'recent_card_events': recent_card_events,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. CUSTOMER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_customers_list_view(request):
    """Searchable, filterable, paginated customer list."""
    qs = User.objects.select_related('profile').annotate(
        cards_count=Count('cards', distinct=True),
        websites_count=Count('websites', distinct=True),
        orders_count=Count('orders', distinct=True),
    ).order_by('-date_joined')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(email__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(cards__card_code__icontains=q) |
            Q(websites__slug__icontains=q)
        ).distinct()

    # Filter status
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)
    elif status_filter == 'staff':
        qs = qs.filter(is_staff=True)

    # Pagination
    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    try:
        customers = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        customers = paginator.page(1)

    return render(request, 'operations/customers_list.html', {
        'customers': customers,
        'search_query': q,
        'status_filter': status_filter,
        'total_count': paginator.count,
    })


@staff_required
def operations_customer_detail_view(request, user_id):
    """Detailed customer view showing profile, cards, websites, orders, and operational controls."""
    customer = get_object_or_404(User.objects.select_related('profile'), id=user_id)
    profile = getattr(customer, 'profile', None)

    cards = customer.cards.all().order_by('-created_at')
    websites = customer.websites.all().order_by('-created_at')
    orders = customer.orders.all().order_by('-created_at')

    # Quick analytics summary
    analytics_summary = None
    if profile:
        analytics_summary = AnalyticsEvent.objects.filter(profile=profile).aggregate(
            taps=Count('id', filter=Q(event_type__in=[AnalyticsEvent.TYPE_CARD_TAP, AnalyticsEvent.TYPE_QR_SCAN])),
            views=Count('id', filter=Q(event_type=AnalyticsEvent.TYPE_PROFILE_VIEW)),
            clicks=Count('id', filter=Q(event_type__in=[
                AnalyticsEvent.TYPE_WHATSAPP, AnalyticsEvent.TYPE_CALL,
                AnalyticsEvent.TYPE_EMAIL, AnalyticsEvent.TYPE_SOCIAL,
                AnalyticsEvent.TYPE_VCARD
            ])),
        )

    # Unassigned cards for quick assignment dropdown
    unassigned_cards = Card.objects.filter(status=Card.STATUS_UNASSIGNED).order_by('card_code')[:50]

    return render(request, 'operations/customer_detail.html', {
        'customer': customer,
        'profile': profile,
        'cards': cards,
        'websites': websites,
        'orders': orders,
        'analytics_summary': analytics_summary,
        'unassigned_cards': unassigned_cards,
    })


@staff_required
@require_POST
def operations_customer_toggle_status_view(request, user_id):
    """Suspend or restore a customer account."""
    customer = get_object_or_404(User, id=user_id)

    # Prevent suspending yourself
    if customer.id == request.user.id:
        messages.error(request, "You cannot suspend your own account.")
        return redirect('operations:customer_detail', user_id=customer.id)

    old_status = "Active" if customer.is_active else "Suspended"
    customer.is_active = not customer.is_active
    new_status = "Active" if customer.is_active else "Suspended"
    customer.save(update_fields=['is_active'])

    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_CUSTOMER_STATUS,
        staff_user=request.user,
        target_repr=f"Customer {customer.email}",
        target_model="User",
        target_id=str(customer.id),
        previous_state=old_status,
        new_state=new_status,
        details=f"Account status changed to {new_status}",
        ip_address=get_client_ip(request),
    )

    messages.success(request, f"Customer {customer.email} has been {new_status.lower()}.")
    return redirect('operations:customer_detail', user_id=customer.id)


# ─────────────────────────────────────────────────────────────────────────────
# 3. NFC CARD INVENTORY
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_cards_list_view(request):
    """Card inventory list with search, status filters, and pagination."""
    qs = Card.objects.select_related('user', 'profile').order_by('card_code')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(card_code__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(profile__full_name__icontains=q)
        )

    # Status Filter
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all' and status_filter in dict(Card.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    # Material Filter
    material_filter = request.GET.get('material', 'all')
    if material_filter != 'all' and material_filter in dict(Card.MATERIAL_CHOICES):
        qs = qs.filter(material=material_filter)

    # Quick summary counts
    status_counts = Card.objects.aggregate(
        total=Count('id'),
        unassigned=Count('id', filter=Q(status=Card.STATUS_UNASSIGNED)),
        active=Count('id', filter=Q(status=Card.STATUS_ACTIVE)),
        suspended=Count('id', filter=Q(status=Card.STATUS_SUSPENDED)),
        lost=Count('id', filter=Q(status=Card.STATUS_LOST)),
        replaced=Count('id', filter=Q(status=Card.STATUS_REPLACED)),
    )

    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    try:
        cards = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        cards = paginator.page(1)

    return render(request, 'operations/cards_list.html', {
        'cards': cards,
        'search_query': q,
        'status_filter': status_filter,
        'material_filter': material_filter,
        'status_counts': status_counts,
        'status_choices': Card.STATUS_CHOICES,
        'total_count': paginator.count,
    })


@staff_required
def operations_card_create_view(request):
    """Add a single card to inventory."""
    if request.method == 'POST':
        card_code = request.POST.get('card_code', '').strip().upper()
        material = request.POST.get('material', 'matte_black')
        activation_pin = request.POST.get('activation_pin', '').strip().upper()

        if not card_code:
            messages.error(request, "Card ID / Code is required.")
            return render(request, 'operations/card_create.html')

        # Format validation
        if not re.match(r'^[A-Z0-9_\-]+$', card_code):
            messages.error(request, "Card ID can only contain uppercase letters, numbers, hyphens, and underscores.")
            return render(request, 'operations/card_create.html', {'card_code': card_code})

        if Card.objects.filter(card_code=card_code).exists():
            messages.error(request, f"Card '{card_code}' already exists in inventory.")
            return render(request, 'operations/card_create.html', {'card_code': card_code})

        card = Card(
            card_code=card_code,
            material=material if material in dict(Card.MATERIAL_CHOICES) else 'matte_black',
            status=Card.STATUS_UNASSIGNED,
        )

        if activation_pin:
            card.set_activation_code(activation_pin)
        else:
            generated_pin = card.generate_activation_code()

        card.save()

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_CREATED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state="",
            new_state=Card.STATUS_UNASSIGNED,
            details=f"Added card to inventory with material {card.get_material_display()}",
            ip_address=get_client_ip(request),
        )

        messages.success(request, f"Card '{card.card_code}' added to inventory successfully.")
        return redirect('operations:card_detail', card_id=card.id)

    return render(request, 'operations/card_create.html', {
        'material_choices': Card.MATERIAL_CHOICES,
    })


@staff_required
def operations_card_bulk_create_view(request):
    """Bulk generate sequential unassigned cards."""
    if request.method == 'POST':
        prefix = request.POST.get('prefix', 'UZY-CARD-').strip().upper()
        start_num_str = request.POST.get('start_number', '1').strip()
        count_str = request.POST.get('count', '20').strip()
        material = request.POST.get('material', 'matte_black')

        try:
            start_num = int(start_num_str)
            count = int(count_str)
        except ValueError:
            messages.error(request, "Starting number and count must be valid integers.")
            return render(request, 'operations/card_bulk_create.html')

        if count < 1 or count > 100:
            messages.error(request, "Bulk creation is limited to 1–100 cards per batch.")
            return render(request, 'operations/card_bulk_create.html')

        created_cards = []
        with transaction.atomic():
            for i in range(count):
                code = f"{prefix}{start_num + i:06d}"
                if not Card.objects.filter(card_code=code).exists():
                    card = Card(
                        card_code=code,
                        material=material if material in dict(Card.MATERIAL_CHOICES) else 'matte_black',
                        status=Card.STATUS_UNASSIGNED,
                    )
                    card.generate_activation_code()
                    card.save()
                    created_cards.append(card)

            AdminAuditLog.log(
                action=AdminAuditLog.ACTION_CARD_BULK_CREATED,
                staff_user=request.user,
                target_repr=f"Batch {prefix} ({len(created_cards)} cards)",
                target_model="Card",
                target_id="",
                previous_state="",
                new_state=Card.STATUS_UNASSIGNED,
                details=f"Bulk generated {len(created_cards)} sequential cards starting at {start_num}",
                ip_address=get_client_ip(request),
            )

        messages.success(request, f"Successfully created {len(created_cards)} new unassigned cards in batch.")
        return redirect('operations:cards_list')

    # Detect recommended next number
    last_card = Card.objects.filter(card_code__startswith='UZY-CARD-').order_by('-card_code').first()
    next_num = 1
    if last_card:
        try:
            num_part = last_card.card_code.replace('UZY-CARD-', '')
            next_num = int(num_part) + 1
        except ValueError:
            pass

    return render(request, 'operations/card_bulk_create.html', {
        'next_num': next_num,
        'material_choices': Card.MATERIAL_CHOICES,
    })


@staff_required
def operations_card_detail_view(request, card_id):
    """Detailed card view with complete operational actions and audit trail."""
    card = get_object_or_404(Card.objects.select_related('user', 'profile', 'replacement_for'), id=card_id)
    card_events = card.events.all()[:25]
    audit_trail = AdminAuditLog.objects.filter(target_model='Card', target_id=str(card.id)).order_by('-created_at')[:20]

    # Customers list for assignment
    customers = User.objects.filter(is_active=True).order_by('email')[:100]
    # Unassigned cards for replacement
    unassigned_cards = Card.objects.filter(status=Card.STATUS_UNASSIGNED).exclude(id=card.id)[:50]

    return render(request, 'operations/card_detail.html', {
        'card': card,
        'card_events': card_events,
        'audit_trail': audit_trail,
        'customers': customers,
        'unassigned_cards': unassigned_cards,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. CARD ASSIGNMENT & STATUS MUTATIONS (ATOMIC & AUDITED)
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
@require_POST
def operations_card_assign_view(request, card_id):
    """Assign an unassigned card to a customer."""
    user_id = request.POST.get('user_id')
    customer = get_object_or_404(User, id=user_id)
    profile = getattr(customer, 'profile', None)

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)

        if card.status == Card.STATUS_ACTIVE and card.user and card.user != customer:
            messages.error(request, f"Card '{card.card_code}' is already assigned to {card.user.email}. Use Reassign instead.")
            return redirect('operations:card_detail', card_id=card.id)

        prev_status = card.status
        prev_owner = card.user.email if card.user else "Unassigned"

        card.user = customer
        card.profile = profile
        card.status = Card.STATUS_ACTIVE
        if not card.activated_at:
            card.activated_at = timezone.now()
        card.save()

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_ASSIGNED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=f"{prev_status} ({prev_owner})",
            new_state=f"ACTIVE ({customer.email})",
            details=f"Assigned card to customer {customer.email}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{card.card_code}' successfully assigned to {customer.email}.")
    return redirect('operations:card_detail', card_id=card.id)


@staff_required
@require_POST
def operations_card_reassign_view(request, card_id):
    """Reassign a card from one customer to another with confirmation."""
    confirm = request.POST.get('confirm_reassign')
    if confirm != 'yes':
        messages.error(request, "Reassignment confirmation required.")
        return redirect('operations:card_detail', card_id=card_id)

    new_user_id = request.POST.get('new_user_id')
    new_customer = get_object_or_404(User, id=new_user_id)
    new_profile = getattr(new_customer, 'profile', None)

    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_owner = card.user.email if card.user else "Unassigned"
        prev_status = card.status

        card.user = new_customer
        card.profile = new_profile
        card.status = Card.STATUS_ACTIVE
        card.activated_at = timezone.now()
        card.save()

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_REASSIGNED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=f"Owner: {prev_owner}",
            new_state=f"Owner: {new_customer.email}",
            details=f"Reassigned card from {prev_owner} to {new_customer.email}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{card.card_code}' reassigned from {prev_owner} to {new_customer.email}.")
    return redirect('operations:card_detail', card_id=card.id)


@staff_required
@require_POST
def operations_card_suspend_view(request, card_id):
    """Suspend an active card."""
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
            details=f"Card suspended by staff",
            ip_address=get_client_ip(request),
        )

    messages.warning(request, f"Card '{card.card_code}' has been SUSPENDED. Public taps will display suspended notice.")
    return redirect('operations:card_detail', card_id=card.id)


@staff_required
@require_POST
def operations_card_restore_view(request, card_id):
    """Restore a suspended card back to ACTIVE."""
    with transaction.atomic():
        card = Card.objects.select_for_update().get(id=card_id)
        prev_status = card.status
        card.status = Card.STATUS_ACTIVE
        card.save(update_fields=['status'])

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_RESTORED,
            staff_user=request.user,
            target_repr=f"Card {card.card_code}",
            target_model="Card",
            target_id=str(card.id),
            previous_state=prev_status,
            new_state=Card.STATUS_ACTIVE,
            details=f"Card restored to active status",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{card.card_code}' has been RESTORED to active status.")
    return redirect('operations:card_detail', card_id=card.id)


@staff_required
@require_POST
def operations_card_mark_lost_view(request, card_id):
    """Mark a card as LOST."""
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
            details=f"Card marked as lost",
            ip_address=get_client_ip(request),
        )

    messages.error(request, f"Card '{card.card_code}' has been marked as LOST.")
    return redirect('operations:card_detail', card_id=card.id)


@staff_required
@require_POST
def operations_card_replace_view(request, card_id):
    """
    Issue a replacement card for an old card.
    The old card is marked REPLACED and links to the new card.
    The customer retains their profile and gains the new card.
    """
    replacement_card_id = request.POST.get('replacement_card_id')
    if not replacement_card_id:
        messages.error(request, "Please select an unassigned replacement card.")
        return redirect('operations:card_detail', card_id=card_id)

    with transaction.atomic():
        old_card = Card.objects.select_for_update().get(id=card_id)
        new_card = Card.objects.select_for_update().get(id=replacement_card_id)

        if new_card.status != Card.STATUS_UNASSIGNED:
            messages.error(request, "Replacement card must be currently UNASSIGNED.")
            return redirect('operations:card_detail', card_id=card_id)

        customer = old_card.user
        profile = old_card.profile

        # Transition old card to REPLACED and point to new card
        old_card.status = Card.STATUS_REPLACED
        old_card.replacement_for = new_card
        old_card.save(update_fields=['status', 'replacement_for'])

        # Transition new card to ACTIVE and link customer
        new_card.user = customer
        new_card.profile = profile
        new_card.status = Card.STATUS_ACTIVE
        new_card.activated_at = timezone.now()
        new_card.save()

        AdminAuditLog.log(
            action=AdminAuditLog.ACTION_CARD_REPLACED,
            staff_user=request.user,
            target_repr=f"Card {old_card.card_code} → {new_card.card_code}",
            target_model="Card",
            target_id=str(old_card.id),
            previous_state=f"Card: {old_card.card_code}",
            new_state=f"Replaced by: {new_card.card_code}",
            details=f"Card {old_card.card_code} replaced with {new_card.card_code} for customer {customer.email if customer else 'None'}",
            ip_address=get_client_ip(request),
        )

    messages.success(request, f"Card '{old_card.card_code}' marked as REPLACED. Customer successfully linked to '{new_card.card_code}'.")
    return redirect('operations:card_detail', card_id=new_card.id)


# ─────────────────────────────────────────────────────────────────────────────
# 5. WEBSITE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_websites_list_view(request):
    """List customer websites with search, status filters, and publish controls."""
    qs = Website.objects.select_related('user', 'user__profile').order_by('-created_at')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(slug__icontains=q) |
            Q(domain__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q)
        )

    # Status Filter
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all' and status_filter in dict(Website.STATUS_CHOICES):
        qs = qs.filter(status=status_filter)

    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    try:
        websites = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        websites = paginator.page(1)

    return render(request, 'operations/websites_list.html', {
        'websites': websites,
        'search_query': q,
        'status_filter': status_filter,
        'status_choices': Website.STATUS_CHOICES,
        'total_count': paginator.count,
    })


@staff_required
@require_POST
def operations_website_toggle_publish_view(request, website_id):
    """Toggle website publish/unpublish status server-side."""
    website = get_object_or_404(Website, id=website_id)
    prev_status = website.status

    if website.status == Website.STATUS_PUBLISHED:
        website.status = Website.STATUS_UNPUBLISHED
        new_status = Website.STATUS_UNPUBLISHED
        msg = f"Website '{website.title}' has been UNPUBLISHED."
    else:
        website.status = Website.STATUS_PUBLISHED
        new_status = Website.STATUS_PUBLISHED
        msg = f"Website '{website.title}' has been PUBLISHED."

    website.save(update_fields=['status'])

    AdminAuditLog.log(
        action=AdminAuditLog.ACTION_WEBSITE_STATUS,
        staff_user=request.user,
        target_repr=f"Website {website.title} ({website.slug})",
        target_model="Website",
        target_id=str(website.id),
        previous_state=prev_status,
        new_state=new_status,
        details=msg,
        ip_address=get_client_ip(request),
    )

    messages.success(request, msg)
    return redirect('operations:websites_list')


# ─────────────────────────────────────────────────────────────────────────────
# 6. ORDER OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_orders_list_view(request):
    """List customer orders with status filters, search, and details."""
    qs = Order.objects.select_related('user', 'package', 'card_assigned').order_by('-created_at')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(order_number__icontains=q) |
            Q(user__email__icontains=q) |
            Q(shipping_name__icontains=q) |
            Q(shipping_phone__icontains=q)
        )

    # Status Filters
    payment_filter = request.GET.get('payment_status', 'all')
    if payment_filter != 'all':
        qs = qs.filter(payment_status=payment_filter)

    order_filter = request.GET.get('order_status', 'all')
    if order_filter != 'all':
        qs = qs.filter(order_status=order_filter)

    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    try:
        orders = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        orders = paginator.page(1)

    return render(request, 'operations/orders_list.html', {
        'orders': orders,
        'search_query': q,
        'payment_filter': payment_filter,
        'order_filter': order_filter,
        'payment_choices': Order.PAYMENT_STATUS_CHOICES,
        'order_status_choices': Order.ORDER_STATUS_CHOICES,
        'total_count': paginator.count,
    })



@staff_required
def operations_order_detail_view(request, order_number):
    """Full order detail view for staff. Shows all customer, payment, fulfillment, and card info."""
    order = get_object_or_404(
        Order.objects.select_related('user', 'package', 'card_assigned'),
        order_number=order_number,
    )
    requirement = getattr(order, 'requirement', None)
    payments = order.payments.all().order_by('-created_at') if hasattr(order, 'payments') else []

    # Card assignment options
    unassigned_cards = Card.objects.filter(status=Card.STATUS_UNASSIGNED).order_by('card_code')[:100]

    # Timeline index for display
    timeline_keys = [step[0] for step in Order.TIMELINE_STEPS]
    try:
        current_step_idx = timeline_keys.index(order.order_status)
    except ValueError:
        current_step_idx = 0

    return render(request, 'operations/order_detail.html', {
        'order': order,
        'requirement': requirement,
        'payments': payments,
        'unassigned_cards': unassigned_cards,
        'timeline_steps': Order.TIMELINE_STEPS,
        'current_step_idx': current_step_idx,
        'order_status_choices': Order.ORDER_STATUS_CHOICES,
        'payment_status_choices': Order.PAYMENT_STATUS_CHOICES,
    })


@staff_required
@require_POST
def operations_order_update_status_view(request, order_number):
    """Update order_status or payment_status from the operations portal."""
    order = get_object_or_404(Order, order_number=order_number)

    new_order_status = request.POST.get('order_status', '').strip()
    new_payment_status = request.POST.get('payment_status', '').strip()

    valid_order_statuses = [c[0] for c in Order.ORDER_STATUS_CHOICES]
    valid_payment_statuses = [c[0] for c in Order.PAYMENT_STATUS_CHOICES]

    changed = []

    if new_order_status and new_order_status != order.order_status:
        if new_order_status not in valid_order_statuses:
            messages.error(request, "Invalid order status.")
            return redirect('operations:order_detail', order_number=order.order_number)
        old_status = order.get_order_status_display()
        order.order_status = new_order_status
        changed.append(f"Order status: {old_status} → {order.get_order_status_display()}")

    if new_payment_status and new_payment_status != order.payment_status:
        if new_payment_status not in valid_payment_statuses:
            messages.error(request, "Invalid payment status.")
            return redirect('operations:order_detail', order_number=order.order_number)
        old_pstatus = order.get_payment_status_display()
        order.payment_status = new_payment_status
        changed.append(f"Payment status: {old_pstatus} → {order.get_payment_status_display()}")

    # Assign card
    assign_card_id = request.POST.get('assign_card_id', '').strip()
    if assign_card_id:
        try:
            card = Card.objects.select_for_update().get(id=assign_card_id, status=Card.STATUS_UNASSIGNED)
            order.card_assigned = card
            changed.append(f"Card assigned: {card.card_code}")
        except Card.DoesNotExist:
            messages.error(request, "Card not found or no longer unassigned.")
            return redirect('operations:order_detail', order_number=order.order_number)

    if changed:
        with transaction.atomic():
            order.save()
            AdminAuditLog.log(
                action=AdminAuditLog.ACTION_ORDER_STATUS,
                staff_user=request.user,
                target_repr=f"Order #{order.order_number}",
                details="; ".join(changed),
            )
        messages.success(request, f"Order #{order.order_number} updated: {'; '.join(changed)}")
    else:
        messages.info(request, "No changes were made.")

    return redirect('operations:order_detail', order_number=order.order_number)


# ─────────────────────────────────────────────────────────────────────────────
# 7. AUDIT LOGS
# ─────────────────────────────────────────────────────────────────────────────
@staff_required
def operations_audit_logs_view(request):
    """View searchable, filterable administrative audit logs."""
    qs = AdminAuditLog.objects.select_related('staff_user').order_by('-created_at')

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(target_repr__icontains=q) |
            Q(staff_user__email__icontains=q) |
            Q(details__icontains=q)
        )

    # Filter action
    action_filter = request.GET.get('action', 'all')
    if action_filter != 'all':
        qs = qs.filter(action=action_filter)

    paginator = Paginator(qs, 50)
    page = request.GET.get('page', 1)
    try:
        logs = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        logs = paginator.page(1)

    return render(request, 'operations/audit_logs.html', {
        'logs': logs,
        'search_query': q,
        'action_filter': action_filter,
        'action_choices': AdminAuditLog.ACTION_CHOICES,
        'total_count': paginator.count,
    })


# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS INQUIRIES — Phase 14
# ─────────────────────────────────────────────────────────────────────────────

from .models import BusinessInquiry


@staff_required
def operations_inquiries_list_view(request):
    """Paginated, searchable, filterable list of business inquiries."""
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    service_filter = request.GET.get('service', '').strip()
    business_type_filter = request.GET.get('business_type', '').strip()

    qs = BusinessInquiry.objects.select_related('assigned_staff').order_by('-created_at')

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q) |
            Q(company_name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if service_filter:
        qs = qs.filter(service_type=service_filter)
    if business_type_filter:
        qs = qs.filter(business_type=business_type_filter)

    paginator = Paginator(qs, 25)
    page = request.GET.get('page')
    try:
        inquiries = paginator.page(page)
    except PageNotAnInteger:
        inquiries = paginator.page(1)
    except EmptyPage:
        inquiries = paginator.page(paginator.num_pages)

    # Status summary counts via a single aggregate query
    counts_map = dict(BusinessInquiry.objects.values_list('status').annotate(c=Count('id')))
    status_summary = [
        {
            'key': sc[0],
            'label': sc[1],
            'count': counts_map.get(sc[0], 0),
        }
        for sc in BusinessInquiry.STATUS_CHOICES
    ]

    return render(request, 'operations/inquiries_list.html', {
        'inquiries': inquiries,
        'search_query': q,
        'status_filter': status_filter,
        'service_filter': service_filter,
        'business_type_filter': business_type_filter,
        'status_choices': BusinessInquiry.STATUS_CHOICES,
        'service_choices': BusinessInquiry.SERVICE_CHOICES,
        'business_type_choices': BusinessInquiry.BUSINESS_TYPE_CHOICES,
        'status_summary': status_summary,
        'total_count': paginator.count,
    })


@staff_required
def operations_inquiry_detail_view(request, inquiry_id):
    """Detail view: shows all inquiry fields, pipeline status, and staff notes. Handles note/save POST."""
    inquiry = get_object_or_404(BusinessInquiry, id=inquiry_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_notes':
            inquiry.admin_notes = request.POST.get('admin_notes', '').strip()
            inquiry.save(update_fields=['admin_notes', 'updated_at'])
            messages.success(request, "Notes saved.")
        return redirect('operations:inquiry_detail', inquiry_id=inquiry_id)

    return render(request, 'operations/inquiry_detail.html', {
        'inquiry': inquiry,
        'status_choices': BusinessInquiry.STATUS_CHOICES,
    })


@staff_required
@require_POST
def operations_inquiry_update_status_view(request, inquiry_id):
    """POST-only: changes pipeline status of a business inquiry."""
    inquiry = get_object_or_404(BusinessInquiry, id=inquiry_id)
    new_status = request.POST.get('status', '').strip()
    valid_statuses = [s[0] for s in BusinessInquiry.STATUS_CHOICES]
    if new_status in valid_statuses:
        old_status = inquiry.get_status_display()
        inquiry.status = new_status
        inquiry.save(update_fields=['status', 'updated_at'])
        messages.success(
            request,
            f"Status updated: {old_status} → {inquiry.get_status_display()}"
        )
    else:
        messages.error(request, "Invalid status.")
    return redirect('operations:inquiry_detail', inquiry_id=inquiry_id)
