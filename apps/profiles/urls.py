from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('u/<slug:slug>/', views.public_profile_view, name='public_profile'),
    path('u/<slug:slug>/vcard/', views.download_vcard_view, name='download_vcard'),
    path('u/<slug:slug>/exchange/', views.submit_contact_exchange_view, name='submit_contact_exchange'),
    path('u/<slug:slug>/qr/', views.download_profile_qr_view, name='download_profile_qr'),
]

