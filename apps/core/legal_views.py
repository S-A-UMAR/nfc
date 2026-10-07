from django.shortcuts import render, redirect
from django.contrib import messages
from apps.core.forms import ContactForm
from apps.core.security import check_rate_limit, get_client_ip


LEGAL_NAV_ITEMS = [
    {'code': 'privacy', 'title': 'Privacy Policy', 'url_name': 'legal:privacy', 'desc': 'NDPA 2023 compliance, data collection & user rights'},
    {'code': 'terms', 'title': 'Terms of Service', 'url_name': 'legal:terms', 'desc': 'Platform rules, account terms & service conditions'},
    {'code': 'cookies', 'title': 'Cookie Policy', 'url_name': 'legal:cookies', 'desc': 'Essential session & security cookies disclosure'},
    {'code': 'acceptable_use', 'title': 'Acceptable Use Policy', 'url_name': 'legal:acceptable_use', 'desc': 'Prohibited activities, fraud prevention & safety'},
    {'code': 'refunds', 'title': 'Refund & Cancellation', 'url_name': 'legal:refunds', 'desc': 'Card hardware returns, production & payment policies'},
    {'code': 'shipping', 'title': 'Shipping & Delivery', 'url_name': 'legal:shipping', 'desc': 'Nigeria courier coverage, timeframes & tracking'},
    {'code': 'nfc_terms', 'title': 'NFC Card Terms', 'url_name': 'legal:nfc_terms', 'desc': 'NTAG216 chip architecture, QR fallback & deactivation'},
    {'code': 'copyright', 'title': 'IP & Copyright Policy', 'url_name': 'legal:copyright', 'desc': 'Trademark rights, user ownership & DMCA/NDPA notices'},
    {'code': 'user_content', 'title': 'User-Generated Content', 'url_name': 'legal:user_content', 'desc': 'Profile media, representations & moderation'},
    {'code': 'third_party', 'title': 'Third-Party Disclosure', 'url_name': 'legal:third_party', 'desc': 'Paystack, Brevo, TiDB, Cloudinary & Render integrations'},
    {'code': 'complaints', 'title': 'Complaints & Inquiries', 'url_name': 'legal:complaints', 'desc': 'Formal dispute resolution, privacy requests & contacts'},
]


def legal_context(current_code):
    """Helper to inject shared legal navigation into all legal pages."""
    return {
        'legal_nav_items': LEGAL_NAV_ITEMS,
        'current_legal_code': current_code,
    }


def legal_index_view(request):
    """Overview hub for all UZYRA legal and compliance policies."""
    ctx = legal_context('index')
    return render(request, 'legal/index.html', ctx)


def privacy_policy_view(request):
    """Privacy Policy conforming to Nigeria Data Protection Act 2023."""
    ctx = legal_context('privacy')
    return render(request, 'legal/privacy.html', ctx)


def terms_of_service_view(request):
    """Terms of Service for UZYRA digital profiles and NFC smart cards."""
    ctx = legal_context('terms')
    return render(request, 'legal/terms.html', ctx)


def cookie_policy_view(request):
    """Cookie Policy documenting strictly essential platform cookies."""
    ctx = legal_context('cookies')
    return render(request, 'legal/cookies.html', ctx)


def acceptable_use_view(request):
    """Acceptable Use Policy prohibiting fraud, phishing, and abuse."""
    ctx = legal_context('acceptable_use')
    return render(request, 'legal/acceptable_use.html', ctx)


def refund_policy_view(request):
    """Refund and Cancellation Policy for hardware cards and digital services."""
    ctx = legal_context('refunds')
    return render(request, 'legal/refunds.html', ctx)


def shipping_policy_view(request):
    """Shipping and Delivery Policy covering courier fulfillment across Nigeria."""
    ctx = legal_context('shipping')
    return render(request, 'legal/shipping.html', ctx)


def nfc_terms_view(request):
    """Technical and operational terms for physical NFC hardware cards."""
    ctx = legal_context('nfc_terms')
    return render(request, 'legal/nfc_terms.html', ctx)


def copyright_policy_view(request):
    """Intellectual Property and Copyright Notice and Takedown Policy."""
    ctx = legal_context('copyright')
    return render(request, 'legal/copyright.html', ctx)


def user_content_view(request):
    """User-Generated Content rules for public profiles and media uploads."""
    ctx = legal_context('user_content')
    return render(request, 'legal/user_content.html', ctx)


def third_party_view(request):
    """Disclosure of verified third-party cloud and infrastructure providers."""
    ctx = legal_context('third_party')
    return render(request, 'legal/third_party.html', ctx)


def complaints_view(request):
    """
    Formal complaints and data subject privacy request intake.
    Allows submitting access/rectification/deletion requests or legal notices.
    """
    if request.method == 'POST':
        ip = get_client_ip(request)
        allowed, remaining, retry_after = check_rate_limit(f"complaint:{ip}", limit=5, window_seconds=600)
        if not allowed:
            messages.error(request, f"Too many submissions. Please wait {retry_after} seconds before trying again.")
            return redirect('legal:complaints')

        form = ContactForm(request.POST)
        if form.is_valid():
            complaint = form.save()
            messages.success(
                request,
                "Your inquiry / formal complaint has been received. Our compliance team will review "
                "and respond within 1–2 business days (or statutory 30 days for NDPA data subject requests)."
            )
            return redirect('legal:complaints')
        else:
            messages.error(request, "Please check the form below. Some required fields need your attention.")
    else:
        # Pre-fill subject if category passed via query parameter
        initial = {}
        category = request.GET.get('category', '').strip()
        if category:
            category_map = {
                'privacy': '[Data Privacy Request] Access / Correction / Deletion',
                'copyright': '[IP / Copyright Notice] Content Infringement Report',
                'card': '[NFC Hardware] Defective Chip / Delivery Issue',
                'refund': '[Payment / Billing] Refund / Cancellation Inquiry',
                'abuse': '[Abuse Report] Impersonation / Fraudulent Profile',
            }
            if category in category_map:
                initial['subject'] = category_map[category]
        form = ContactForm(initial=initial)

    ctx = legal_context('complaints')
    ctx['form'] = form
    return render(request, 'legal/complaints.html', ctx)
