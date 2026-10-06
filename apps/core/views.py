from django.shortcuts import render, redirect
from django.contrib import messages
from apps.orders.models import ProductPackage
from apps.profiles.models import Profile
from .forms import ContactForm, BusinessInquiryForm

def home_view(request):
    packages = ProductPackage.objects.filter(is_active=True)[:4]
    demo_profile = Profile.objects.first()
    return render(request, 'core/home.html', {
        'packages': packages,
        'demo_profile': demo_profile,
    })

def smart_card_view(request):
    return render(request, 'core/smart_card.html')

def websites_view(request):
    packages = ProductPackage.objects.filter(package_type__in=['personal_website', 'business_website'], is_active=True)
    return render(request, 'core/websites.html', {'packages': packages})

def how_it_works_view(request):
    return render(request, 'core/how_it_works.html')

def pricing_view(request):
    packages = ProductPackage.objects.filter(is_active=True)
    return render(request, 'core/pricing.html', {'packages': packages})

def about_view(request):
    return render(request, 'core/about.html')

def faq_view(request):
    faq_items = [
        ("Does it work on iPhone?", "Yes. NFC works natively on iPhone 7 and all later models (iOS 11+) without any app. Simply tap your card to the top area of the phone."),
        ("Does it work on Android?", "Yes. NFC is supported on virtually all modern Android smartphones. Go to Settings and ensure NFC is enabled."),
        ("Do I need an app to use or share the card?", "No. The person tapping your card needs zero apps. The card opens a URL in their default web browser instantly."),
        ("What happens if I lose my card?", "Log in to your dashboard and click 'Report Lost'. The card is instantly deactivated and will no longer redirect to your profile. You can then request a replacement card."),
        ("Can I change my information after receiving the card?", "Yes — unlimited times. Log in to your dashboard and update anything. Changes are live immediately without any physical modification to the card."),
        ("Does the card require charging or a battery?", "No. The NFC chip is passive and powered by the electromagnetic field from the reading phone. It requires no battery and never runs out of power."),
        ("Does NFC require internet on the card?", "No. The card itself has no internet connection. The phone that reads the card uses its own internet connection to open your digital profile link."),
        ("What if someone's phone doesn't support NFC?", "Every card includes a precision-printed QR code that points to the same URL. The visitor simply opens their camera app and scans the code instead."),
        ("How long does it take to receive my card?", "Delivery typically takes 5-10 business days within Nigeria after your design is approved."),
        ("Can I order multiple cards?", "Yes. You can order individual additional cards or bulk fleet cards for your team. Contact us for corporate/fleet pricing."),
        ("Can businesses get cards for all their employees?", "Yes. We offer corporate fleet packages with centralized management, uniform branding, and volume discounts. Contact our enterprise sales team."),
    ]
    return render(request, 'core/faq.html', {'faq_items': faq_items})

def contact_view(request):
    from apps.core.security import check_rate_limit, get_client_ip
    if request.method == 'POST':
        # Rate limit: max 5 contact submissions per IP per 10 minutes
        ip = get_client_ip(request)
        allowed, remaining, retry_after = check_rate_limit(f"contact:{ip}", limit=5, window_seconds=600)
        if not allowed:
            messages.error(request, f"Too many contact submissions. Please wait {retry_after} seconds before trying again.")
            return redirect('core:contact')

        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you! Your message has been received. Our team will get back to you shortly.")
            return redirect('core:contact')
    else:
        form = ContactForm()
    return render(request, 'core/contact.html', {'form': form})

def error_403_view(request, exception=None):
    return render(request, 'core/403.html', status=403)

def error_404_view(request, exception=None):
    return render(request, 'core/404.html', status=404)

def error_500_view(request):
    return render(request, 'core/500.html', status=500)


def business_view(request):
    """
    Business & Custom Solutions page — Coming Soon.
    Redirects all access until the feature is ready for public launch.
    """
    messages.info(request, "Our Business & Custom Solutions page is coming soon. Contact us on WhatsApp in the meantime.")
    return redirect('core:home')


# ─────────────────────────────────────────────────────────────────────────────
# SEO
# ─────────────────────────────────────────────────────────────────────────────
from django.http import HttpResponse

def robots_txt_view(request):
    """
    Serve robots.txt to guide search engine crawlers.
    Private/internal areas are blocked; public profiles and websites are allowed.
    """
    lines = [
        "User-agent: *",
        "",
        "# Private areas — do not index",
        "Disallow: /dashboard/",
        "Disallow: /operations/",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /payments/",
        "Disallow: /orders/",
        "Disallow: /analytics/",
        "Disallow: /site/preview/",
        "",
        "# Public areas — allowed",
        "Allow: /u/",
        "Allow: /site/",
        "Allow: /c/",
        "",
        "# Sitemap",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
