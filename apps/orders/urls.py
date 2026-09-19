from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('checkout/<slug:package_code>/', views.checkout_view, name='checkout'),
]
