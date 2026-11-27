"""
Data migration: backfill setup_completed=True for any Profile that
already has all 6 checklist items satisfied.

This fixes the regression where migration 0009 defaulted all profiles
to False, so users who had completed setup saw the widget re-appear
whenever they removed a field.

The 6 checklist criteria (mirrors dashboard_views.py):
  1. identity  — full_name AND slug are set
  2. headline  — title OR business_name is set
  3. bio       — bio OR business_description is set
  4. contact   — phone OR whatsapp OR email is set
  5. photo     — profile_image OR business_logo is set
  6. links     — has at least one social_link OR custom_link

A profile that passed all 6 is treated as "ever-completed" and
latched True permanently, matching the intent of the original latch.
"""
from django.db import migrations


def backfill_setup_completed(apps, schema_editor):
    Profile = apps.get_model('profiles', 'Profile')

    for profile in Profile.objects.filter(setup_completed=False).iterator():
        # 1 — identity
        ok_identity = bool(profile.full_name and profile.slug)
        # 2 — headline
        ok_headline = bool(profile.title or profile.business_name)
        # 3 — bio
        ok_bio = bool(profile.bio or profile.business_description)
        # 4 — contact
        ok_contact = bool(profile.phone or profile.whatsapp or profile.email)
        # 5 — photo
        ok_photo = bool(profile.profile_image or profile.business_logo)
        # 6 — links  (use related managers available via apps registry)
        ok_links = (
            profile.social_links.exists() or profile.custom_links.exists()
        )

        if all([ok_identity, ok_headline, ok_bio, ok_contact, ok_photo, ok_links]):
            profile.setup_completed = True
            profile.save(update_fields=['setup_completed'])


def reverse_backfill(apps, schema_editor):
    # Non-destructive reverse: just leave setup_completed as-is
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0009_profile_setup_completed'),
    ]

    operations = [
        migrations.RunPython(backfill_setup_completed, reverse_backfill),
    ]
