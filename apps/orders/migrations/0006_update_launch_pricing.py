from django.db import migrations


def update_launch_pricing(apps, schema_editor):
    """
    Update ProductPackage prices to the approved STRIDE launch pricing structure
    without modifying historical Order.amount or Payment.amount records.
    """
    ProductPackage = apps.get_model('orders', 'ProductPackage')

    updates = {
        'smart-card': {
            'price_ngn': 15000,
        },
        'personal-suite': {
            'price_ngn': 25000,
            'features': (
                'Premium Matte Obsidian NFC Smart Card Included\n'
                'Custom Laser-Engraved Full Name & Handle\n'
                'Verified Digital Profile with Custom Username Link\n'
                'Direct Link Mode (Instant Routing to WhatsApp/LinkedIn)\n'
                '15+ Luxury Theme Styles & Custom Color Palettes\n'
                'Bio, Services & Project Showcase Hub\n'
                'Real-time Tap & Scan Interaction Analytics\n'
                'Tracked Nationwide Delivery (Fee Communicated Separately)\n'
                'Lifetime Access — Buy Once, Own Forever'
            ),
        },
        'corporate-fleet': {
            'price_ngn': 0,
            'badge': 'Request a Quote',
            'features': (
                'Custom Laser-Engraved NFC Cards with Company Branding\n'
                'Centralized Company Management Portal\n'
                'Standardized Corporate Identity for All Staff\n'
                'Team Tap, Engagement & Networking Analytics\n'
                'Rapid Card Reassignment for New Employees\n'
                'Dedicated Corporate Account Manager & Priority Support\n'
                'Luxury Presentation Gift Box Packaging\n'
                'Custom Volume & Delivery Quotation'
            ),
        },
    }

    for code, fields in updates.items():
        ProductPackage.objects.filter(code=code).update(**fields)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_order_shipping_carrier_and_more'),
    ]

    operations = [
        migrations.RunPython(update_launch_pricing, migrations.RunPython.noop),
    ]
