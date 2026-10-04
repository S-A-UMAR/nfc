from django.urls import path
from apps.accounts import dashboard_views as acc_dash
from apps.profiles import views as prof_views
from apps.cards import views as card_views
from apps.orders import views as order_views
from apps.websites import views as web_views
from apps.analytics import views as ana_views

app_name = 'dashboard'

urlpatterns = [
    path('', acc_dash.dashboard_overview_view, name='overview'),
    path('profile/', prof_views.profile_edit_view, name='profile_edit'),
    path('links/', prof_views.links_manage_view, name='links_manage'),
    path('links/social/add/', prof_views.add_social_link_view, name='add_social_link'),
    path('links/social/edit/<int:link_id>/', prof_views.edit_social_link_view, name='edit_social_link'),
    path('links/social/toggle/<int:link_id>/', prof_views.toggle_social_link_view, name='toggle_social_link'),
    path('links/social/delete/<int:link_id>/', prof_views.delete_social_link_view, name='delete_social_link'),
    path('links/custom/add/', prof_views.add_custom_link_view, name='add_custom_link'),
    path('links/custom/edit/<int:link_id>/', prof_views.edit_custom_link_view, name='edit_custom_link'),
    path('links/custom/toggle/<int:link_id>/', prof_views.toggle_custom_link_view, name='toggle_custom_link'),
    path('links/custom/delete/<int:link_id>/', prof_views.delete_custom_link_view, name='delete_custom_link'),
    path('card/', card_views.card_manage_view, name='card_manage'),
    path('orders/', order_views.order_list_view, name='orders_list'),
    path('orders/<str:order_number>/', order_views.order_detail_view, name='order_detail'),
    path('orders/<str:order_number>/submit-info/', order_views.order_submit_info_view, name='order_submit_info'),
    path('website/', web_views.website_manage_view, name='website_manage'),
    path('website/<int:website_id>/publish/', web_views.website_publish_toggle, name='website_publish'),
    path('website/<int:website_id>/service/add/', web_views.service_create_view, name='service_add'),
    path('website/service/<int:service_id>/edit/', web_views.service_edit_view, name='service_edit'),
    path('website/service/<int:service_id>/toggle/', web_views.service_toggle_active_view, name='service_toggle'),
    path('website/service/<int:service_id>/delete/', web_views.service_delete_view, name='service_delete'),
    path('website/<int:website_id>/product/add/', web_views.product_create_view, name='product_add'),
    path('website/product/<int:product_id>/edit/', web_views.product_edit_view, name='product_edit'),
    path('website/product/<int:product_id>/toggle/', web_views.product_toggle_active_view, name='product_toggle'),
    path('website/product/<int:product_id>/delete/', web_views.product_delete_view, name='product_delete'),
    path('analytics/', ana_views.analytics_dashboard_view, name='analytics_view'),
    path('appearance/', prof_views.profile_appearance_view, name='appearance'),
    path('settings/', acc_dash.settings_view, name='settings_view'),
]
