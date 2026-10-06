from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Website, WebsiteChangeRequest, Service, Product
from .forms import WebsiteChangeRequestForm, WebsiteBuilderForm, ServiceForm, ProductForm
from apps.profiles.models import Profile

@login_required
def website_manage_view(request):
    """Customer Dashboard Website Builder — Coming Soon."""
    # Website Builder is not yet available. Redirect all access.
    messages.info(request, "Website Builder is coming soon. We'll notify you when it's ready.")
    return redirect('dashboard:overview')


@login_required
def website_publish_toggle(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    if website.status == Website.STATUS_PUBLISHED:
        website.status = Website.STATUS_UNPUBLISHED
        messages.info(request, "Website has been unpublished and is now private.")
    else:
        website.status = Website.STATUS_PUBLISHED
        messages.success(request, "Congratulations! Your website is now live.")
    website.save()
    return redirect('dashboard:website_manage')


# --- SERVICES CRUD ---
@login_required
def service_create_view(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.website = website
            service.save()
            messages.success(request, f"Service '{service.name}' added successfully.")
        else:
            errors = "; ".join([f"{f}: {err[0]}" for f, err in form.errors.items()])
            messages.error(request, f"Could not add service: {errors}")
    return redirect('dashboard:website_manage')

@login_required
def service_edit_view(request, service_id):
    service = get_object_or_404(Service, id=service_id, website__user=request.user)
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, f"Service '{service.name}' updated successfully.")
        else:
            errors = "; ".join([f"{f}: {err[0]}" for f, err in form.errors.items()])
            messages.error(request, f"Could not update service: {errors}")
    return redirect('dashboard:website_manage')

@login_required
@require_POST
def service_toggle_active_view(request, service_id):
    service = get_object_or_404(Service, id=service_id, website__user=request.user)
    service.is_active = not service.is_active
    service.save()
    status_label = "visible" if service.is_active else "hidden"
    messages.success(request, f"Service '{service.name}' is now {status_label} on your website.")
    return redirect('dashboard:website_manage')

@login_required
def service_delete_view(request, service_id):
    service = get_object_or_404(Service, id=service_id, website__user=request.user)
    if request.method == 'POST':
        name = service.name
        service.delete()
        messages.success(request, f"Service '{name}' was deleted.")
    return redirect('dashboard:website_manage')


# --- PRODUCTS CRUD ---
@login_required
def product_create_view(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.website = website
            product.save()
            messages.success(request, f"Product '{product.name}' added successfully.")
        else:
            errors = "; ".join([f"{f}: {err[0]}" for f, err in form.errors.items()])
            messages.error(request, f"Could not add product: {errors}")
    return redirect('dashboard:website_manage')

@login_required
def product_edit_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, website__user=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f"Product '{product.name}' updated successfully.")
        else:
            errors = "; ".join([f"{f}: {err[0]}" for f, err in form.errors.items()])
            messages.error(request, f"Could not update product: {errors}")
    return redirect('dashboard:website_manage')

@login_required
@require_POST
def product_toggle_active_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, website__user=request.user)
    product.is_active = not product.is_active
    product.save()
    status_label = "visible" if product.is_active else "hidden"
    messages.success(request, f"Product '{product.name}' is now {status_label} on your website.")
    return redirect('dashboard:website_manage')

@login_required
def product_delete_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, website__user=request.user)
    if request.method == 'POST':
        name = product.name
        product.delete()
        messages.success(request, f"Product '{name}' was deleted.")
    return redirect('dashboard:website_manage')


# --- PREVIEW / TEMPLATES ---
def template_preview_view(request, template_code):
    """Static template showcases."""
    # (Existing static dictionary code here - truncated for brevity)
    templates = {
        'modern_business': {'name': 'Modern Business'},
        'luxury_atelier': {'name': 'Luxury Atelier'},
        'creator_portfolio': {'name': 'Creator Portfolio'},
        'retail_showcase': {'name': 'Retail Showcase'},
    }
    return render(request, 'websites/template_preview.html', {
        'template_code': template_code,
        'data': templates.get(template_code, templates['modern_business']),
    })

from apps.analytics.models import AnalyticsEvent

VALID_TEMPLATES = {'modern_business', 'luxury_atelier', 'creator_portfolio', 'retail_showcase'}

def public_website_view(request, slug):
    """The live public website rendered for visitors."""
    website = get_object_or_404(Website, slug=slug, status=Website.STATUS_PUBLISHED)
    profile = website.user.profile
    
    # Log anonymous website view analytics event
    AnalyticsEvent.objects.create(
        profile=profile,
        website=website,
        event_type=AnalyticsEvent.TYPE_WEBSITE_PAGE_VIEW,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
        referer=request.META.get('HTTP_REFERER', '')[:255]
    )
    
    template_choice = website.template_choice if website.template_choice in VALID_TEMPLATES else 'modern_business'
    return render(request, f'websites/templates/{template_choice}.html', {
        'website': website,
        'profile': profile,
        'services': website.services.filter(is_active=True).order_by('display_order', 'id'),
        'products': website.products.filter(is_active=True).order_by('display_order', 'id'),
        'social_links': profile.social_links.filter(is_active=True),
        'is_preview': False,
    })

@login_required
def preview_website_view(request, slug):
    """Private preview of the website, reflecting unsaved/saved data."""
    website = get_object_or_404(Website, slug=slug, user=request.user)
    profile = website.user.profile
    
    template_choice = website.template_choice if website.template_choice in VALID_TEMPLATES else 'modern_business'
    return render(request, f'websites/templates/{template_choice}.html', {
        'website': website,
        'profile': profile,
        'services': website.services.filter(is_active=True).order_by('display_order', 'id'),
        'products': website.products.filter(is_active=True).order_by('display_order', 'id'),
        'social_links': profile.social_links.filter(is_active=True),
        'is_preview': True,
    })
