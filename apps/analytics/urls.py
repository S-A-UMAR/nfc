from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('track/', views.track_event_api, name='track_event'),
    path('track/website-cta/', views.website_cta_track_view, name='track_website_cta'),
]
