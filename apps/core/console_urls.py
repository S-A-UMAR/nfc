from django.urls import path
from . import console_views as views

app_name = 'console'

urlpatterns = [
    # 1. Overview
    path('', views.console_overview_view, name='overview'),

    # 2. Cards Inventory & Details
    path('cards/', views.console_cards_list_view, name='cards_list'),
    path('cards/generate/', views.console_card_generate_view, name='card_generate'),
    path('cards/<int:card_id>/', views.console_card_detail_view, name='card_detail'),
    path('cards/<int:card_id>/update-stage/', views.console_card_update_stage_view, name='card_update_stage'),

    # 3. Provisioning Downloads & Exports
    path('cards/<int:card_id>/qr/png/', views.console_card_qr_download_png, name='card_qr_png'),
    path('cards/<int:card_id>/qr/svg/', views.console_card_qr_download_svg, name='card_qr_svg'),
    path('cards/manifest/zip/', views.console_card_batch_export_zip, name='card_batch_export_zip'),

    # 4. Packaging Slips & CSV Manifest (One-Time Handoff)
    path('cards/packaging/<str:token>/', views.console_card_packaging_view, name='card_packaging'),
    path('cards/packaging/<str:token>/csv/', views.console_packaging_csv_download, name='packaging_csv'),
    path('cards/packaging/<str:token>/print/', views.console_packaging_print_view, name='packaging_print'),
    path('cards/packaging/<str:token>/acknowledge/', views.console_packaging_acknowledge_view, name='packaging_acknowledge'),

    # 5. PIN Regeneration (Manager Only)
    path('cards/<int:card_id>/regenerate-pin/', views.console_card_regenerate_pin_view, name='card_regenerate_pin'),

    # 6. Card Lifecycle Mutations (Atomic)
    path('cards/<int:card_id>/assign/', views.console_card_assign_view, name='card_assign'),
    path('cards/<int:card_id>/reassign/', views.console_card_reassign_view, name='card_reassign'),
    path('cards/<int:card_id>/suspend/', views.console_card_suspend_view, name='card_suspend'),
    path('cards/<int:card_id>/restore/', views.console_card_restore_view, name='card_restore'),
    path('cards/<int:card_id>/mark-lost/', views.console_card_mark_lost_view, name='card_mark_lost'),
    path('cards/<int:card_id>/replace/', views.console_card_replace_view, name='card_replace'),

    # 7. Orders & Fulfillment
    path('orders/', views.console_orders_list_view, name='orders_list'),
    path('orders/<str:order_number>/', views.console_order_detail_view, name='order_detail'),
    path('orders/<str:order_number>/update-status/', views.console_order_update_status_view, name='order_update_status'),

    # 8. Customers Directory
    path('customers/', views.console_customers_list_view, name='customers_list'),
    path('customers/<int:user_id>/', views.console_customer_detail_view, name='customer_detail'),
    path('customers/<int:user_id>/toggle-status/', views.console_customer_toggle_status_view, name='customer_toggle_status'),

    # 9. Inquiries CRM
    path('inquiries/', views.console_inquiries_list_view, name='inquiries_list'),
    path('inquiries/<int:inquiry_id>/', views.console_inquiry_detail_view, name='inquiry_detail'),
    path('inquiries/<int:inquiry_id>/update-status/', views.console_inquiry_update_status_view, name='inquiry_update_status'),

    # 10. Websites CMS
    path('websites/', views.console_websites_list_view, name='websites_list'),
    path('websites/<int:website_id>/toggle-publish/', views.console_website_toggle_publish_view, name='website_toggle_publish'),

    # 11. Audit Logs
    path('audit-logs/', views.console_audit_logs_view, name='audit_logs'),
]
