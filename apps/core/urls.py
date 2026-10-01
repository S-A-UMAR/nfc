from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('smart-card/', views.smart_card_view, name='smart_card'),
    path('websites/', views.websites_view, name='websites'),
    path('how-it-works/', views.how_it_works_view, name='how_it_works'),
    path('pricing/', views.pricing_view, name='pricing'),
    path('about/', views.about_view, name='about'),
    path('faq/', views.faq_view, name='faq'),
    path('contact/', views.contact_view, name='contact'),
    path('business/', views.business_view, name='business'),
]
