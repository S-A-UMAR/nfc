from django.urls import path
from . import views

app_name = 'websites'

urlpatterns = [
    path('preview/<slug:template_code>/', views.template_preview_view, name='template_preview'),
]
