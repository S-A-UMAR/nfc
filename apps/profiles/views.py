from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Profile, SocialLink, CustomLink
from .forms import ProfileForm, SocialLinkForm, CustomLinkForm
from apps.analytics.models import AnalyticsEvent

def public_profile_view(request, slug):
    """
    Mobile-First Public Digital Profile (/u/<slug>/).
    Renders the live profile with instant contact actions, social icons, and links.
    """
    profile = get_object_or_404(Profile.objects.select_related('user'), slug=slug)
    social_links = profile.social_links.filter(is_active=True)
    custom_links = profile.custom_links.filter(is_active=True)

    # Log anonymous profile view analytics event
    AnalyticsEvent.objects.create(
        profile=profile,
        event_type=AnalyticsEvent.TYPE_PROFILE_VIEW,
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
        referer=request.META.get('HTTP_REFERER', '')[:255]
    )

    return render(request, 'profiles/public_profile.html', {
        'profile': profile,
        'social_links': social_links,
        'custom_links': custom_links,
    })


def download_vcard_view(request, slug):
    """
    Generates an RFC 2426 compliant .vcf contact card file.
    When tapped on mobile, iOS / Android prompts the user to save the contact directly to phone contacts.
    """
    profile = get_object_or_404(Profile, slug=slug)

    # Log vCard download analytics event
    AnalyticsEvent.objects.create(
        profile=profile,
        event_type=AnalyticsEvent.TYPE_VCARD,
        target_label="vCard Download",
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:255]
    )

    def _clean_vcard(text):
        if not text:
            return ""
        return str(text).replace('\r', '').replace('\n', ' ').replace(';', '\\;').strip()

    clean_name = _clean_vcard(profile.full_name)
    vcard_lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{clean_name}",
        f"N:{clean_name};;;;",
    ]

    if profile.business_name:
        vcard_lines.append(f"ORG:{_clean_vcard(profile.business_name)}")
    if profile.title:
        vcard_lines.append(f"TITLE:{_clean_vcard(profile.title)}")
    if profile.phone:
        vcard_lines.append(f"TEL;TYPE=CELL,VOICE:{_clean_vcard(profile.phone)}")
    if profile.email:
        vcard_lines.append(f"EMAIL;TYPE=PREF,INTERNET:{_clean_vcard(profile.email)}")
    if profile.website_url:
        vcard_lines.append(f"URL:{_clean_vcard(profile.website_url)}")
    if profile.bio:
        vcard_lines.append(f"NOTE:{_clean_vcard(profile.bio)}")
    if profile.address:
        vcard_lines.append(f"ADR;TYPE=WORK:;;{_clean_vcard(profile.address)};;;;")

    vcard_lines.append("END:VCARD")
    vcard_content = "\r\n".join(vcard_lines) + "\r\n"

    import re
    safe_slug = re.sub(r'[^a-zA-Z0-9_\-]', '', profile.slug) or 'contact'
    response = HttpResponse(vcard_content, content_type='text/vcard; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{safe_slug}_contact.vcf"'
    return response


@login_required
def profile_edit_view(request):
    """Dashboard profile manager."""
    profile, created = Profile.objects.get_or_create(
        user=request.user,
        defaults={'full_name': request.user.display_name, 'email': request.user.email}
    )

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your digital profile has been updated successfully.")
            return redirect('dashboard:profile_edit')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'dashboard/profile_edit.html', {
        'profile': profile,
        'form': form,
    })


@login_required
def links_manage_view(request):
    """Dashboard link manager (social links and custom buttons)."""
    profile = request.user.profile
    social_links = profile.social_links.all()
    custom_links = profile.custom_links.all()
    social_form = SocialLinkForm()
    custom_form = CustomLinkForm()

    return render(request, 'dashboard/links_manage.html', {
        'profile': profile,
        'social_links': social_links,
        'custom_links': custom_links,
        'social_form': social_form,
        'custom_form': custom_form,
    })


@login_required
@require_POST
def add_social_link_view(request):
    """Add a new social link."""
    profile = request.user.profile
    form = SocialLinkForm(request.POST)
    if form.is_valid():
        link = form.save(commit=False)
        link.profile = profile
        link.order = profile.social_links.count() + 1
        link.save()
        messages.success(request, f"{link.get_platform_display()} link added.")
    else:
        messages.error(request, "Could not add social link. Please check the URL format.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def delete_social_link_view(request, link_id):
    """Delete a social link."""
    link = get_object_or_404(SocialLink, id=link_id, profile__user=request.user)
    name = link.get_platform_display()
    link.delete()
    messages.info(request, f"{name} link removed.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def edit_social_link_view(request, link_id):
    """Edit an existing social link."""
    link = get_object_or_404(SocialLink, id=link_id, profile__user=request.user)
    form = SocialLinkForm(request.POST, instance=link)
    if form.is_valid():
        form.save()
        messages.success(request, f"{link.get_platform_display()} link updated.")
    else:
        messages.error(request, "Could not update social link.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def toggle_social_link_view(request, link_id):
    """Toggle active/disabled status for a social link."""
    link = get_object_or_404(SocialLink, id=link_id, profile__user=request.user)
    link.is_active = not link.is_active
    link.save()
    status_str = "enabled" if link.is_active else "disabled"
    messages.info(request, f"{link.get_platform_display()} link {status_str}.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def add_custom_link_view(request):
    """Add a new custom CTA button."""
    profile = request.user.profile
    form = CustomLinkForm(request.POST)
    if form.is_valid():
        link = form.save(commit=False)
        link.profile = profile
        link.position = profile.custom_links.count() + 1
        link.save()
        messages.success(request, f"Button '{link.title}' added.")
    else:
        messages.error(request, "Could not add button. Please check the inputs.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def delete_custom_link_view(request, link_id):
    """Delete a custom CTA button."""
    link = get_object_or_404(CustomLink, id=link_id, profile__user=request.user)
    title = link.title
    link.delete()
    messages.info(request, f"Button '{title}' removed.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def edit_custom_link_view(request, link_id):
    """Edit an existing custom CTA button."""
    link = get_object_or_404(CustomLink, id=link_id, profile__user=request.user)
    form = CustomLinkForm(request.POST, instance=link)
    if form.is_valid():
        form.save()
        messages.success(request, f"Button '{link.title}' updated.")
    else:
        messages.error(request, "Could not update button.")
    return redirect('dashboard:links_manage')


@login_required
@require_POST
def toggle_custom_link_view(request, link_id):
    """Toggle active/disabled status for a custom button."""
    link = get_object_or_404(CustomLink, id=link_id, profile__user=request.user)
    link.is_active = not link.is_active
    link.save()
    status_str = "enabled" if link.is_active else "disabled"
    messages.info(request, f"Button '{link.title}' {status_str}.")
    return redirect('dashboard:links_manage')
