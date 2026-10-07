from django.urls import path
from . import legal_views as views

app_name = 'legal'

urlpatterns = [
    path('', views.legal_index_view, name='index'),
    path('privacy/', views.privacy_policy_view, name='privacy'),
    path('terms/', views.terms_of_service_view, name='terms'),
    path('cookies/', views.cookie_policy_view, name='cookies'),
    path('acceptable-use/', views.acceptable_use_view, name='acceptable_use'),
    path('refunds/', views.refund_policy_view, name='refunds'),
    path('shipping/', views.shipping_policy_view, name='shipping'),
    path('nfc-terms/', views.nfc_terms_view, name='nfc_terms'),
    path('copyright/', views.copyright_policy_view, name='copyright'),
    path('user-content/', views.user_content_view, name='user_content'),
    path('third-party/', views.third_party_view, name='third_party'),
    path('complaints/', views.complaints_view, name='complaints'),
]
