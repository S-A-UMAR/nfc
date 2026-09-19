from django.urls import path
from . import views

app_name = 'cards'

urlpatterns = [
    path('c/<str:card_code>/', views.nfc_redirect_view, name='nfc_redirect'),
    path('activate/', views.card_activate_view, name='card_activate'),
    path('report-lost/<int:card_id>/', views.card_report_lost_view, name='card_report_lost'),
]
