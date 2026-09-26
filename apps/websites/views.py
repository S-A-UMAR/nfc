from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Website, WebsiteChangeRequest, Service, Product
from .forms import WebsiteChangeRequestForm, WebsiteBuilderForm, ServiceForm, ProductForm
from apps.profiles.models import Profile

@login_required
def website_manage_view(request):
    """Customer Dashboard Website Builder."""
    website = Website.objects.filter(user=request.user).first()
    
    if not website:
        # Empty state: Create website
        if request.method == 'POST':
            profile = getattr(request.user, 'profile', None)
            title = request.POST.get('title', f"{request.user.display_name}'s Website")
            website = Website.objects.create(
                user=request.user,
                title=title,
                status=Website.STATUS_DRAFT
            )
            messages.success(request, "Website created! You can now customize it.")
            return redirect('dashboard:website_manage')
        return render(request, 'dashboard/website_create.html')

    # Website exists, show builder
    if request.method == 'POST' and 'update_website' in request.POST:
        form = WebsiteBuilderForm(request.POST, instance=website)
        if form.is_valid():
            form.save()
            messages.success(request, "Website settings saved successfully.")
            return redirect('dashboard:website_manage')
    else:
        form = WebsiteBuilderForm(instance=website)

    services = website.services.all()
    products = website.products.all()
    
    return render(request, 'dashboard/website_manage.html', {
        'website': website,
        'form': form,
        'services': services,
        'products': products,
    })

@login_required
def website_publish_toggle(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    if website.status == Website.STATUS_PUBLISHED:
        website.status = Website.STATUS_UNPUBLISHED
        messages.info(request, "Website has been unpublished and is now private.")
    else:
        website.status = Website.STATUS_PUBLISHED
        messages.success(request, "Website is now live and published!")
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
            messages.success(request, "Service added.")
    return redirect('dashboard:website_manage')

@login_required
def service_edit_view(request, service_id):
    service = get_object_or_404(Service, id=service_id, website__user=request.user)
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, "Service updated.")
    return redirect('dashboard:website_manage')

@login_required
def service_delete_view(request, service_id):
    service = get_object_or_404(Service, id=service_id, website__user=request.user)
    if request.method == 'POST':
        service.delete()
        messages.success(request, "Service deleted.")
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
            messages.success(request, "Product added.")
    return redirect('dashboard:website_manage')

@login_required
def product_edit_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, website__user=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Product updated.")
    return redirect('dashboard:website_manage')

@login_required
def product_delete_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, website__user=request.user)
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Product deleted.")
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

def public_website_view(request, slug):
    """The live public website rendered for visitors."""
    website = get_object_or_404(Website, slug=slug, status=Website.STATUS_PUBLISHED)
    profile = website.user.profile
    
    return render(request, f'websites/templates/{website.template_choice}.html', {
        'website': website,
        'profile': profile,
        'services': website.services.filter(is_active=True),
        'products': website.products.filter(is_active=True),
        'social_links': profile.social_links.filter(is_active=True),
        'is_preview': False,
    })

@login_required
def preview_website_view(request, slug):
    """Private preview of the website, reflecting unsaved/saved data."""
    website = get_object_or_404(Website, slug=slug, user=request.user)
    profile = website.user.profile
    
    return render(request, f'websites/templates/{website.template_choice}.html', {
        'website': website,
        'profile': profile,
        'services': website.services.filter(is_active=True),
        'products': website.products.filter(is_active=True),
        'social_links': profile.social_links.filter(is_active=True),
        'is_preview': True,
    })
