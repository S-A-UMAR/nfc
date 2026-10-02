import os
import sys
import json
import django
from importlib import import_module

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.orders.models import Order
from apps.cards.models import Card

User = get_user_model()
admin_user = User.objects.filter(is_staff=True).first()
if not admin_user:
    admin_user = User.objects.create_superuser('admin@uzyra.com', 'admin@uzyra.com', 'AdminPass123!')

# Get valid order and card
sample_order = Order.objects.first()
order_num = sample_order.order_number if sample_order else 'ORD-1024'
sample_card = Card.objects.first()
card_id = sample_card.id if sample_card else 1

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
session = SessionStore()
session[django.contrib.auth.SESSION_KEY] = str(admin_user.pk)
session[django.contrib.auth.BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
session[django.contrib.auth.HASH_SESSION_KEY] = admin_user.get_session_auth_hash()
session.save()

pages = [
    # Customer Dashboard
    {"category": "Dashboard", "name": "Workspace Overview", "url": "http://127.0.0.1:8000/dashboard/"},
    {"category": "Dashboard", "name": "Profile Edit", "url": "http://127.0.0.1:8000/dashboard/profile/"},
    {"category": "Dashboard", "name": "Digital Links", "url": "http://127.0.0.1:8000/dashboard/links/"},
    {"category": "Dashboard", "name": "Smart Card Management", "url": "http://127.0.0.1:8000/dashboard/card/"},
    {"category": "Dashboard", "name": "Card Activation", "url": "http://127.0.0.1:8000/cards/activate/"},
    {"category": "Dashboard", "name": "Analytics Dashboard", "url": "http://127.0.0.1:8000/dashboard/analytics/"},
    {"category": "Dashboard", "name": "Website Builder", "url": "http://127.0.0.1:8000/dashboard/website/"},
    {"category": "Dashboard", "name": "Orders List", "url": "http://127.0.0.1:8000/dashboard/orders/"},
    {"category": "Dashboard", "name": "Order Detail", "url": f"http://127.0.0.1:8000/dashboard/orders/{order_num}/"},
    {"category": "Dashboard", "name": "Order Submit Info", "url": f"http://127.0.0.1:8000/dashboard/orders/{order_num}/submit-info/"},
    {"category": "Dashboard", "name": "Account Settings", "url": "http://127.0.0.1:8000/dashboard/settings/"},

    # Admin / Operations
    {"category": "Operations", "name": "Operations Hub", "url": "http://127.0.0.1:8000/operations/"},
    {"category": "Operations", "name": "Customer Directory", "url": "http://127.0.0.1:8000/operations/customers/"},
    {"category": "Operations", "name": "Customer Detail", "url": f"http://127.0.0.1:8000/operations/customers/{admin_user.id}/"},
    {"category": "Operations", "name": "Card Inventory", "url": "http://127.0.0.1:8000/operations/cards/"},
    {"category": "Operations", "name": "Card Add Single", "url": "http://127.0.0.1:8000/operations/cards/add/"},
    {"category": "Operations", "name": "Card Bulk Add", "url": "http://127.0.0.1:8000/operations/cards/bulk-add/"},
    {"category": "Operations", "name": "Card Detail & Lifecycle", "url": f"http://127.0.0.1:8000/operations/cards/{card_id}/"},
    {"category": "Operations", "name": "Website Operations", "url": "http://127.0.0.1:8000/operations/websites/"},
    {"category": "Operations", "name": "Order Operations", "url": "http://127.0.0.1:8000/operations/orders/"},
    {"category": "Operations", "name": "Audit Logs", "url": "http://127.0.0.1:8000/operations/audit-logs/"},
]

viewports = [320, 360, 375, 390, 414, 430, 768, 820, 1024, 1280, 1440]

print(f"Loaded {len(pages)} pages across {len(viewports)} viewports = {len(pages) * len(viewports)} audits.")
