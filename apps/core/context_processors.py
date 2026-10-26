from django.conf import settings

def brand_context(request):
    """Provides global brand settings and notification counts to all Django templates."""
    user_profile = None
    unread_contacts_count = 0

    if request.user.is_authenticated:
        user_profile = getattr(request.user, 'profile', None)
        if user_profile:
            try:
                unread_contacts_count = user_profile.received_contacts.filter(is_read=False).count()
            except Exception:
                unread_contacts_count = 0

    return {
        'BRAND_NAME': getattr(settings, 'BRAND_NAME', 'STRIDE'),
        'BRAND_TAGLINE': getattr(settings, 'BRAND_TAGLINE', 'Modern Identity. Seamless Connection.'),
        'BRAND_SUPPORT_EMAIL': getattr(settings, 'BRAND_SUPPORT_EMAIL', 'contact@uzyra.com'),
        'BRAND_SUPPORT_PHONE': getattr(settings, 'BRAND_SUPPORT_PHONE', '+234 800 000 0000'),
        'PAYSTACK_PUBLIC_KEY': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'user_profile': user_profile,
        'unread_contacts_count': unread_contacts_count,
    }
