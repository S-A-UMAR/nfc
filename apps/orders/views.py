from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import ProductPackage, Order, OrderRequirement
from .forms import CheckoutForm, OrderRequirementForm

@login_required
def checkout_view(request, package_code):
    """Checkout page for ordering smart cards and website packages."""
    package = get_object_or_404(ProductPackage, code=package_code, is_active=True)
    profile = getattr(request.user, 'profile', None)

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.package = package
            order.amount = package.price_ngn
            order.payment_status = Order.PAYMENT_PENDING
            order.order_status = Order.STATUS_RECEIVED
            order.save()

            messages.success(request, f"Order #{order.order_number} created successfully.")
            return redirect('payments:initialize', order_number=order.order_number)
    else:
        # Pre-fill shipping defaults if profile exists
        initial_data = {
            'shipping_name': profile.full_name if profile else request.user.display_name,
            'shipping_phone': profile.phone if profile else request.user.phone or '',
            'shipping_address': profile.address if profile else '',
        }
        form = CheckoutForm(initial=initial_data)

    return render(request, 'orders/checkout.html', {
        'package': package,
        'form': form,
    })


@login_required
def order_list_view(request):
    """Customer Dashboard orders list."""
    orders = Order.objects.filter(user=request.user).select_related('package')
    return render(request, 'dashboard/orders_list.html', {
        'orders': orders,
    })


@login_required
def order_detail_view(request, order_number):
    """Detailed Order view with interactive progress timeline."""
    order = get_object_or_404(Order.objects.select_related('package', 'user'), order_number=order_number, user=request.user)
    
    # Calculate timeline status indices
    timeline_keys = [step[0] for step in Order.TIMELINE_STEPS]
    try:
        current_step_idx = timeline_keys.index(order.order_status)
    except ValueError:
        current_step_idx = 0

    return render(request, 'dashboard/order_detail.html', {
        'order': order,
        'timeline_steps': Order.TIMELINE_STEPS,
        'current_step_idx': current_step_idx,
    })


@login_required
def order_submit_info_view(request, order_number):
    """Intake form for customer to submit identity & website details after ordering."""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    profile = getattr(request.user, 'profile', None)

    requirement = getattr(order, 'requirement', None)

    if request.method == 'POST':
        form = OrderRequirementForm(request.POST, instance=requirement)
        if form.is_valid():
            req = form.save(commit=False)
            req.order = order
            req.save()

            # Advance order status if it was awaiting info
            if order.order_status in [Order.STATUS_RECEIVED, Order.STATUS_PAID, Order.STATUS_INFO_REQUIRED]:
                order.order_status = Order.STATUS_INFO_SUBMITTED
                order.save()

            messages.success(request, "Your information and design requirements have been submitted! Our team is reviewing them.")
            return redirect('dashboard:order_detail', order_number=order.order_number)
    else:
        if requirement:
            form = OrderRequirementForm(instance=requirement)
        else:
            # Prefill from user profile
            initial = {
                'full_name': profile.full_name if profile else '',
                'title': profile.title if profile else '',
                'bio': profile.bio if profile else '',
                'business_name': profile.business_name if profile else '',
                'business_category': profile.business_category if profile else '',
                'business_description': profile.business_description if profile else '',
                'phone': profile.phone if profile else '',
                'whatsapp': profile.whatsapp if profile else '',
                'email': profile.email if profile else '',
                'address': profile.address if profile else '',
                'website_type': 'business' if 'business' in order.package.package_type else ('personal' if 'personal' in order.package.package_type else 'none')
            }
            form = OrderRequirementForm(initial=initial)

    return render(request, 'dashboard/order_submit_info.html', {
        'order': order,
        'form': form,
    })
