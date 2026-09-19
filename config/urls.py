from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts import views as account_views
from apps.cards import views as card_views
from apps.profiles import views as profile_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Shortcuts for Authentication
    path('login/', account_views.login_view, name='login'),
    path('register/', account_views.register_view, name='register'),
    path('logout/', account_views.logout_view, name='logout'),
    path('auth/', include('apps.accounts.urls', namespace='accounts')),

    # Core Marketing Website
    path('', include('apps.core.urls', namespace='core')),

    # Unified Customer Dashboard
    path('dashboard/', include('apps.core.dashboard_urls', namespace='dashboard')),

    # NFC Redirect Hub: /c/<card_code>/
    path('', include('apps.cards.urls', namespace='cards')),

    # Public Mobile-First Digital Profiles: /u/<slug>/
    path('', include('apps.profiles.urls', namespace='profiles')),

    # Orders & Checkout
    path('orders/', include('apps.orders.urls', namespace='orders')),

    # Payments & Paystack
    path('payments/', include('apps.payments.urls', namespace='payments')),

    # Websites & Template Previews
    path('websites-catalog/', include('apps.websites.urls', namespace='websites')),

    # Analytics Tracking API
    path('analytics/', include('apps.analytics.urls', namespace='analytics')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler403 = 'apps.core.views.error_403_view'
handler404 = 'apps.core.views.error_404_view'
handler500 = 'apps.core.views.error_500_view'
