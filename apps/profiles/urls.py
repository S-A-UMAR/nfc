from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('u/<slug:slug>/', views.public_profile_view, name='public_profile'),
    path('u/<slug:slug>/vcard/', views.download_vcard_view, name='download_vcard'),
]
