from django.urls import path
from . import operations_views as views

app_name = 'operations'

urlpatterns = [
    # Overview
    path('', views.operations_overview_view, name='overview'),

    # Customers
    path('customers/', views.operations_customers_list_view, name='customers_list'),
    path('customers/<int:user_id>/', views.operations_customer_detail_view, name='customer_detail'),
    path('customers/<int:user_id>/toggle-status/', views.operations_customer_toggle_status_view, name='customer_toggle_status'),

    # Card Inventory
    path('cards/', views.operations_cards_list_view, name='cards_list'),
    path('cards/add/', views.operations_card_create_view, name='card_create'),
    path('cards/bulk-add/', views.operations_card_bulk_create_view, name='card_bulk_create'),
    path('cards/<int:card_id>/', views.operations_card_detail_view, name='card_detail'),

    # Card Mutations
    path('cards/<int:card_id>/assign/', views.operations_card_assign_view, name='card_assign'),
    path('cards/<int:card_id>/reassign/', views.operations_card_reassign_view, name='card_reassign'),
    path('cards/<int:card_id>/suspend/', views.operations_card_suspend_view, name='card_suspend'),
    path('cards/<int:card_id>/restore/', views.operations_card_restore_view, name='card_restore'),
    path('cards/<int:card_id>/mark-lost/', views.operations_card_mark_lost_view, name='card_mark_lost'),
    path('cards/<int:card_id>/replace/', views.operations_card_replace_view, name='card_replace'),

    # Websites
    path('websites/', views.operations_websites_list_view, name='websites_list'),
    path('websites/<int:website_id>/toggle-publish/', views.operations_website_toggle_publish_view, name='website_toggle_publish'),

    # Orders
    path('orders/', views.operations_orders_list_view, name='orders_list'),

    # Audit Logs
    path('audit-logs/', views.operations_audit_logs_view, name='audit_logs'),

    # Business Inquiries
    path('inquiries/', views.operations_inquiries_list_view, name='inquiries_list'),
    path('inquiries/<int:inquiry_id>/', views.operations_inquiry_detail_view, name='inquiry_detail'),
    path('inquiries/<int:inquiry_id>/update-status/', views.operations_inquiry_update_status_view, name='inquiry_update_status'),
]
