from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('initialize/<str:order_number>/', views.initialize_payment_view, name='initialize'),
    path('verify/', views.verify_payment_view, name='verify'),
    path('webhook/', views.paystack_webhook_view, name='webhook'),
]
