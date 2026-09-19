from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random

from apps.orders.models import ProductPackage, Order, OrderRequirement
from apps.profiles.models import Profile, SocialLink, CustomLink
from apps.cards.models import Card, CardEvent
from apps.websites.models import Website, WebsiteChangeRequest
from apps.analytics.models import AnalyticsEvent

User = get_user_model()

class Command(BaseCommand):
    help = "Seed database with UZYRA exact design packages, demo users, active cards, orders, and analytics."

    def handle(self, *args, **options):
        self.stdout.write("Starting UZYRA platform seed...")

        # 1. Product Packages (Matching exact image tiers)
        packages_data = [
            {
                'code': 'starter',
                'name': 'Starter',
                'package_type': 'card_only',
                'price_ngn': 15000,
                'description': 'Smart cards, digital profile, and seamless networking for individual professionals.',
                'features': 'Smart Card (NFC + QR)\nDigital Profile\nBasic Support',
                'badge': '',
                'order_index': 1,
            },
            {
                'code': 'personal',
                'name': 'Personal',
                'package_type': 'personal_website',
                'price_ngn': 45000,
                'description': 'Complete personal identity suite with dedicated personal brand website.',
                'features': 'Smart Card\nPersonal Website\nDigital Profile\n1 Year Hosting',
                'badge': '',
                'order_index': 2,
            },
            {
                'code': 'business',
                'name': 'Business',
                'package_type': 'business_website',
                'price_ngn': 80000,
                'description': 'Corporate business website, product catalogue, and smart business cards.',
                'features': 'Smart Card\nBusiness Website\nDigital Profile\nProduct Catalogue\n1 Year Hosting',
                'badge': '',
                'order_index': 3,
            },
            {
                'code': 'business-pro',
                'name': 'Business Pro',
                'package_type': 'business_website',
                'price_ngn': 150000,
                'description': 'Advanced bespoke enterprise design, custom card engraving, and priority engineering.',
                'features': 'Smart Card (Custom)\nAdvanced Website\nProduct Catalogue\nAnalytics Dashboard\nDomain + Hosting (1yr)\nPriority Support',
                'badge': 'Popular',
                'order_index': 4,
            },
        ]

        for pdata in packages_data:
            pkg, created = ProductPackage.objects.update_or_create(
                code=pdata['code'],
                defaults=pdata
            )
            self.stdout.write(f"  Package: {pkg.name} (₦{pkg.price_ngn:,})")

        # 2. Superuser
        admin_email = "admin@uzyra.com"
        admin_user, admin_created = User.objects.get_or_create(
            email=admin_email,
            defaults={
                'first_name': 'UZYRA',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if admin_created:
            admin_user.set_password("admin1234")
            admin_user.save()
            self.stdout.write(f"  Created admin: {admin_email} / admin1234")

        # 3. Demo User: Ahmed Ibrahim (Matching exact image mockup)
        demo_email = "ahmed@example.com"
        demo_user, demo_created = User.objects.get_or_create(
            email=demo_email,
            defaults={
                'first_name': 'Ahmed',
                'last_name': 'Ibrahim',
                'phone': '+234 802 345 6789',
            }
        )
        if demo_created:
            demo_user.set_password("password123")
            demo_user.save()

        profile, _ = Profile.objects.get_or_create(
            user=demo_user,
            defaults={'slug': 'ahmed-ibrahim'}
        )
        profile.full_name = 'Ahmed Ibrahim'
        profile.title = 'Business Consultant | CEO'
        profile.bio = 'Helping businesses grow with smart solutions and digital tools.'
        profile.business_name = 'Ahmed Consulting & Tech Group'
        profile.business_category = 'Business Consulting'
        profile.phone = '+234 802 345 6789'
        profile.whatsapp = '+2348023456789'
        profile.email = 'ahmed@uzyra.com'
        profile.website_url = 'https://uzyra.com'
        profile.location = 'Victoria Island, Lagos'
        profile.address = 'Plot 14B, Admiralty Way, Lekki Phase 1, Lagos, Nigeria'
        profile.theme = 'graphite'
        profile.is_search_indexed = True
        profile.save()

        # Social links: Instagram, X, LinkedIn, YouTube, TikTok
        SocialLink.objects.filter(profile=profile).delete()
        socials = [
            ('instagram', 'https://instagram.com/ahmedibrahim', '@ahmedibrahim'),
            ('x_twitter', 'https://x.com/ahmedibrahim', '@ahmedibrahim'),
            ('linkedin', 'https://linkedin.com/in/ahmed-ibrahim', 'Ahmed Ibrahim'),
            ('youtube', 'https://youtube.com/@ahmedibrahim', 'Ahmed Ibrahim'),
            ('tiktok', 'https://tiktok.com/@ahmedibrahim', '@ahmedibrahim'),
        ]
        for idx, (plat, url, lbl) in enumerate(socials):
            SocialLink.objects.create(
                profile=profile,
                platform=plat,
                url=url,
                display_label=lbl,
                order=idx + 1,
                is_active=True
            )

        # Custom buttons (Matching the phone accordion items in the image: About Me, My Services, Website, Location)
        CustomLink.objects.filter(profile=profile).delete()
        buttons = [
            ('About Me', '#about-me', 'user', 1),
            ('My Services', '#my-services', 'briefcase', 2),
            ('Website', 'https://uzyra.com', 'globe', 3),
            ('Location', '#location', 'map-pin', 4),
        ]
        for title, url, icon, pos in buttons:
            CustomLink.objects.create(
                profile=profile,
                title=title,
                url=url,
                icon=icon,
                position=pos,
                is_active=True
            )

        # 4. Smart Cards (Matching card ID UZ-000193 in the image)
        card_main, _ = Card.objects.get_or_create(
            card_code='UZ-000193',
            defaults={
                'user': demo_user,
                'profile': profile,
                'status': Card.STATUS_ACTIVE,
                'material': 'matte_black',
                'activated_at': timezone.now() - timedelta(days=60),
            }
        )
        card_main.user = demo_user
        card_main.profile = profile
        card_main.status = Card.STATUS_ACTIVE
        card_main.save()

        # Secondary Card & Lost Card
        Card.objects.get_or_create(
            card_code='UZ-000194',
            defaults={'status': Card.STATUS_ACTIVE, 'user': demo_user, 'profile': profile}
        )
        Card.objects.get_or_create(
            card_code='UZ-000195',
            defaults={'status': Card.STATUS_LOST, 'user': demo_user}
        )
        for i in range(196, 205):
            Card.objects.get_or_create(
                card_code=f"UZ-{i:06d}",
                defaults={'status': Card.STATUS_UNASSIGNED}
            )

        # 5. Demo Order: Business Pro (ORD-1024)
        pkg_pro = ProductPackage.objects.get(code='business-pro')
        order, _ = Order.objects.get_or_create(
            order_number='ORD-1024',
            defaults={
                'user': demo_user,
                'package': pkg_pro,
                'amount': pkg_pro.price_ngn,
                'payment_status': Order.PAYMENT_PAID,
                'order_status': Order.STATUS_DESIGNING,
                'card_assigned': card_main,
                'shipping_name': 'Ahmed Ibrahim',
                'shipping_phone': '+234 802 345 6789',
                'shipping_address': 'Plot 14B, Admiralty Way, Lekki Phase 1',
                'shipping_city': 'Lagos',
                'shipping_state': 'Lagos State',
            }
        )
        OrderRequirement.objects.get_or_create(
            order=order,
            defaults={
                'full_name': 'Ahmed Ibrahim',
                'title': 'Business Consultant | CEO',
                'bio': 'Helping businesses grow with smart solutions and digital tools.',
                'business_name': 'Ahmed Consulting & Tech Group',
                'business_category': 'Consulting',
                'phone': '+234 802 345 6789',
                'whatsapp': '+2348023456789',
                'email': 'ahmed@uzyra.com',
                'website_type': 'business',
                'pages_needed': 'Home, About, Services, Products, Contact',
            }
        )

        # 6. Demo Website: Personal Website
        Website.objects.get_or_create(
            user=demo_user,
            title='Ahmed Ibrahim Personal Website',
            defaults={
                'website_type': 'personal',
                'template_choice': 'modern_business',
                'domain': 'www.ahmedibrahim.com',
                'live_url': 'https://ahmedibrahim.com',
                'status': Website.STATUS_LIVE,
            }
        )

        # 7. Exact Analytics Counts (Matching image: 127 taps, 214 views, 83 visits, 46 whatsapp)
        AnalyticsEvent.objects.filter(profile=profile).delete()
        now = timezone.now()
        counts = [
            (AnalyticsEvent.TYPE_PROFILE_VIEW, 214, "Profile View"),
            (AnalyticsEvent.TYPE_CARD_TAP, 127, "Card Tap"),
            (AnalyticsEvent.TYPE_WEBSITE, 83, "Website Visit"),
            (AnalyticsEvent.TYPE_WHATSAPP, 46, "WhatsApp Click"),
        ]
        for etype, cnt, lbl in counts:
            for _ in range(cnt):
                days_ago = random.randint(0, 25)
                AnalyticsEvent.objects.create(
                    profile=profile,
                    card=card_main if 'card' in etype else None,
                    event_type=etype,
                    target_label=lbl,
                    timestamp=now - timedelta(days=days_ago, hours=random.randint(1, 23))
                )

        self.stdout.write(self.style.SUCCESS("UZYRA platform successfully seeded with exact image parameters!"))
