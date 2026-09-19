from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Profile

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    """Ensure every User model instance automatically gets a linked Profile."""
    if created:
        full_name = f"{instance.first_name} {instance.last_name}".strip() or instance.email.split('@')[0]
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                'full_name': full_name,
                'email': instance.email,
                'phone': getattr(instance, 'phone', '') or '',
                'whatsapp': getattr(instance, 'phone', '') or ''
            }
        )
    else:
        if hasattr(instance, 'profile') and instance.profile:
            instance.profile.save()
