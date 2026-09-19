from django.conf import settings

def brand_context(request):
    """Provides global brand settings to all Django templates."""
    user_profile = None
    if request.user.is_authenticated:
        user_profile = getattr(request.user, 'profile', None)
        
    return {
        'BRAND_NAME': getattr(settings, 'BRAND_NAME', 'ULVA'),
        'BRAND_TAGLINE': getattr(settings, 'BRAND_TAGLINE', 'The Smart Identity & Digital Business Platform'),
        'BRAND_SUPPORT_EMAIL': getattr(settings, 'BRAND_SUPPORT_EMAIL', 'support@ulva.io'),
        'BRAND_SUPPORT_PHONE': getattr(settings, 'BRAND_SUPPORT_PHONE', '+234 800 000 0000'),
        'PAYSTACK_PUBLIC_KEY': getattr(settings, 'PAYSTACK_PUBLIC_KEY', ''),
        'user_profile': user_profile,
    }
