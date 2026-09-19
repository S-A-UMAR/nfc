from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Website, WebsiteChangeRequest
from .forms import WebsiteChangeRequestForm

@login_required
def website_manage_view(request):
    """Customer Dashboard Website management & change requests."""
    websites = Website.objects.filter(user=request.user)
    primary_website = websites.first()
    change_requests = WebsiteChangeRequest.objects.filter(user=request.user)
    form = WebsiteChangeRequestForm()

    return render(request, 'dashboard/website_manage.html', {
        'websites': websites,
        'primary_website': primary_website,
        'change_requests': change_requests,
        'form': form,
    })


@login_required
@require_POST
def website_submit_change_request_view(request, website_id):
    """Submit a change request for a live website."""
    website = get_object_or_404(Website, id=website_id, user=request.user)
    form = WebsiteChangeRequestForm(request.POST)

    if form.is_valid():
        change_req = form.save(commit=False)
        change_req.website = website
        change_req.user = request.user
        change_req.status = WebsiteChangeRequest.STATUS_SUBMITTED
        change_req.save()
        messages.success(request, f"Change Request #{change_req.id} has been submitted to the engineering team.")
    else:
        messages.error(request, "Could not submit request. Please fill out all required fields.")

    return redirect('dashboard:website_manage')


def template_preview_view(request, template_code):
    """Showcase live client templates (Modern Business, Luxury, Portfolio, Retail)."""
    templates = {
        'modern-business': {
            'name': 'Modern Business & Tech Suite',
            'category': 'Agencies, Consultancies & Technology Companies',
            'headline': 'Next-Generation Solutions for Modern Enterprises',
            'tagline': 'We engineer high-performance software and scalable digital infrastructure.',
        },
        'luxury-atelier': {
            'name': 'Luxury Atelier & Haute Couture',
            'category': 'Jewelry, Fashion & Luxury Goods',
            'headline': 'Craftsmanship Refined. Elegance Perfected.',
            'tagline': 'Bespoke hand-crafted timepieces and timeless jewelry.',
        },
        'creator-portfolio': {
            'name': 'Creator & Professional Portfolio',
            'category': 'Architects, Developers & Directors',
            'headline': 'Designing Digital Experiences with Precision',
            'tagline': 'Award-winning creative direction and web architecture.',
        },
    }
    
    selected_template = templates.get(template_code, templates['modern-business'])
    return render(request, 'websites/template_preview.html', {
        'template_code': template_code,
        'data': selected_template,
    })
