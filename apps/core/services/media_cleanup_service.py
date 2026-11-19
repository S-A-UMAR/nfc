import logging
from django.utils import timezone
from django.db.models import Q
from django.apps import apps
import cloudinary.uploader
from apps.core.models import MediaCleanupTask

logger = logging.getLogger('stride.media_cleanup')


class MediaCleanupService:
    """
    Service responsible for reliably deleting orphaned Cloudinary media assets.
    Key properties:
    - Decoupled from core database transactions.
    - Idempotent: already-deleted assets ('not found') are marked completed.
    - Shared asset protection: skips deletion if another database record references the same asset.
    - Durable tracking: failures are recorded in MediaCleanupTask with error diagnostics and retry counts.
    """

    @staticmethod
    def extract_public_id(file_field_or_path) -> str:
        """
        Extracts clean Cloudinary public_id from a FieldFile, URL or path string.
        Returns empty string if invalid, None, or a static default placeholder.
        """
        if not file_field_or_path:
            return ""

        path_str = str(file_field_or_path).strip()
        if not path_str:
            return ""

        # Filter out common local default placeholders
        if path_str.startswith('img/') or path_str.startswith('/static/') or 'default' in path_str.lower() and '/' not in path_str:
            return ""

        # If it's a full Cloudinary URL, extract the public_id
        if 'res.cloudinary.com' in path_str:
            try:
                # Format: https://res.cloudinary.com/<cloud>/image/upload/v<version>/<public_id>.<ext>
                parts = path_str.split('/upload/')
                if len(parts) > 1:
                    after_upload = parts[1]
                    # Strip version if present (e.g. v123456789/)
                    if after_upload.startswith('v') and '/' in after_upload:
                        after_upload = after_upload.split('/', 1)[1]
                    # Strip extension
                    public_id = after_upload.rsplit('.', 1)[0]
                    return public_id
            except Exception:
                pass

        # Standard FieldFile.name storage path (e.g. 'profile_photos/user_123.jpg')
        # In Cloudinary, public_id is typically the path without file extension
        public_id = path_str.rsplit('.', 1)[0]
        return public_id

    @classmethod
    def is_asset_referenced(cls, public_id: str, exclude_user_id: int = None) -> bool:
        """
        Shared Asset Protection:
        Inspects all application models to verify whether public_id is still referenced
        by any active record in the database.
        Optionally excludes records belonging to exclude_user_id (e.g. during account deletion).
        Returns True if the asset is still in use, preventing premature deletion.
        """
        if not public_id:
            return False

        try:
            Profile = apps.get_model('profiles', 'Profile')
            ProfileGalleryItem = apps.get_model('profiles', 'ProfileGalleryItem')
            ProfileTestimonial = apps.get_model('profiles', 'ProfileTestimonial')

            profile_qs = Profile.objects.all()
            gallery_qs = ProfileGalleryItem.objects.all()
            testimonial_qs = ProfileTestimonial.objects.all()

            if exclude_user_id is not None:
                profile_qs = profile_qs.exclude(user_id=exclude_user_id)
                gallery_qs = gallery_qs.exclude(profile__user_id=exclude_user_id)
                testimonial_qs = testimonial_qs.exclude(profile__user_id=exclude_user_id)

            # Check Profile main image fields
            if profile_qs.filter(
                Q(profile_image__icontains=public_id) |
                Q(cover_image__icontains=public_id) |
                Q(business_logo__icontains=public_id)
            ).exists():
                return True

            # Check Gallery Items
            if gallery_qs.filter(image__icontains=public_id).exists():
                return True

            # Check Testimonials
            if testimonial_qs.filter(client_avatar__icontains=public_id).exists():
                return True

            # Check Website Services / Products if website app is present
            try:
                Service = apps.get_model('websites', 'Service')
                Product = apps.get_model('websites', 'Product')
                service_qs = Service.objects.all()
                product_qs = Product.objects.all()

                if exclude_user_id is not None:
                    service_qs = service_qs.exclude(website__user_id=exclude_user_id)
                    product_qs = product_qs.exclude(website__user_id=exclude_user_id)

                if service_qs.filter(image__icontains=public_id).exists():
                    return True
                if product_qs.filter(image__icontains=public_id).exists():
                    return True
            except (LookupError, Exception):
                pass

        except Exception as e:
            logger.warning("Error checking asset reference for %s: %s", public_id, e)
            # Fail safe: if reference check errors, assume in use to prevent accidental data loss
            return True

        return False

    @classmethod
    def enqueue_user_media(cls, user, source_repr: str = None) -> list:
        """
        Inspects a user's associated models and enqueues all distinct media assets
        for Cloudinary cleanup prior to user account deletion.
        """
        if not user:
            return []

        source_repr = source_repr or f"Account deletion for {getattr(user, 'email', str(user))}"
        raw_assets = set()

        # 1. Profile assets
        if hasattr(user, 'profile') and user.profile:
            profile = user.profile
            if profile.profile_image:
                raw_assets.add(cls.extract_public_id(profile.profile_image))
            if profile.cover_image:
                raw_assets.add(cls.extract_public_id(profile.cover_image))
            if profile.business_logo:
                raw_assets.add(cls.extract_public_id(profile.business_logo))

            # Gallery items
            for g_item in profile.gallery_items.all():
                if g_item.image:
                    raw_assets.add(cls.extract_public_id(g_item.image))

            # Testimonials
            for t_item in profile.testimonials.all():
                if t_item.client_avatar:
                    raw_assets.add(cls.extract_public_id(t_item.client_avatar))

        # 2. Website assets
        if hasattr(user, 'websites'):
            for website in user.websites.all():
                if hasattr(website, 'services'):
                    for svc in website.services.all():
                        if svc.image:
                            raw_assets.add(cls.extract_public_id(svc.image))
                if hasattr(website, 'products'):
                    for prd in website.products.all():
                        if prd.image:
                            raw_assets.add(cls.extract_public_id(prd.image))

        created_tasks = []
        for pid in raw_assets:
            clean_pid = (pid or '').strip()
            if not clean_pid:
                continue

            # Idempotency / Duplicate Prevention:
            # Check if an active task for this public_id is already queued or processing
            existing_task = MediaCleanupTask.objects.filter(
                public_id=clean_pid,
                status__in=[MediaCleanupTask.STATUS_PENDING, MediaCleanupTask.STATUS_PROCESSING]
            ).first()

            if existing_task:
                created_tasks.append(existing_task)
                continue

            task = MediaCleanupTask.objects.create(
                public_id=clean_pid,
                resource_type='image',
                status=MediaCleanupTask.STATUS_PENDING,
                source_repr=source_repr[:255]
            )
            created_tasks.append(task)
            logger.info("Enqueued media cleanup task %s for asset: %s", task.id, clean_pid)

        return created_tasks

    @classmethod
    def process_task(cls, task: MediaCleanupTask, exclude_user_id: int = None) -> bool:
        """
        Executes remote Cloudinary deletion for a single MediaCleanupTask.
        Enforces:
        - Max attempt check
        - Shared asset protection (optionally excluding a deleting user)
        - Idempotency ('ok' or 'not found' treated as success)
        - Safe exception handling with diagnostic error logging
        """
        if task.status == MediaCleanupTask.STATUS_COMPLETED:
            return True

        if task.attempts >= task.max_attempts:
            task.status = MediaCleanupTask.STATUS_FAILED
            task.last_error = f"Max attempts ({task.max_attempts}) reached without success."
            task.save(update_fields=['status', 'last_error', 'updated_at'])
            logger.warning("Task %s reached max attempts (%s) for asset %s", task.id, task.max_attempts, task.public_id)
            return False

        # Shared Asset Protection Check
        if cls.is_asset_referenced(task.public_id, exclude_user_id=exclude_user_id):
            task.status = MediaCleanupTask.STATUS_SKIPPED
            task.last_error = "Asset is still referenced by an active database record. Deletion skipped."
            task.completed_at = timezone.now()
            task.save(update_fields=['status', 'last_error', 'completed_at', 'updated_at'])
            logger.info("Skipped deletion of asset %s (referenced by another active record)", task.public_id)
            return True

        task.attempts += 1
        task.status = MediaCleanupTask.STATUS_PROCESSING
        task.save(update_fields=['attempts', 'status', 'updated_at'])

        try:
            # Execute remote Cloudinary deletion
            response = cloudinary.uploader.destroy(
                task.public_id,
                resource_type=task.resource_type,
                invalidate=True
            )

            result = response.get('result') if isinstance(response, dict) else str(response)

            # Cloudinary returns 'ok' when deleted, or 'not found' if already deleted. Both represent success.
            if result in ('ok', 'not found'):
                task.status = MediaCleanupTask.STATUS_COMPLETED
                task.completed_at = timezone.now()
                task.last_error = ""
                task.save(update_fields=['status', 'completed_at', 'last_error', 'updated_at'])
                logger.info("Successfully cleaned up Cloudinary asset %s (result: %s)", task.public_id, result)
                return True
            else:
                task.status = MediaCleanupTask.STATUS_FAILED
                task.last_error = f"Cloudinary returned non-success result: {result}"
                task.save(update_fields=['status', 'last_error', 'updated_at'])
                logger.error("Cloudinary returned non-success for %s: %s", task.public_id, response)
                return False

        except Exception as exc:
            task.status = MediaCleanupTask.STATUS_FAILED
            task.last_error = f"{type(exc).__name__}: {str(exc)}"
            task.save(update_fields=['status', 'last_error', 'updated_at'])
            logger.error("Exception during Cloudinary deletion of %s: %s", task.public_id, exc)
            return False

    @classmethod
    def process_pending_tasks(cls, limit: int = 50, retry_failed: bool = False) -> dict:
        """
        Processes queued MediaCleanupTask entries.
        Returns a summary dictionary of processed results.
        """
        statuses = [MediaCleanupTask.STATUS_PENDING]
        if retry_failed:
            statuses.append(MediaCleanupTask.STATUS_FAILED)

        # Select tasks that have not exceeded max_attempts
        tasks = MediaCleanupTask.objects.filter(
            status__in=statuses,
            attempts__lt=5
        ).order_by('created_at')[:limit]

        summary = {'processed': 0, 'completed': 0, 'failed': 0, 'skipped': 0}

        for task in tasks:
            summary['processed'] += 1
            success = cls.process_task(task)
            # Re-read task status
            task.refresh_from_db(fields=['status'])
            if task.status == MediaCleanupTask.STATUS_COMPLETED:
                summary['completed'] += 1
            elif task.status == MediaCleanupTask.STATUS_SKIPPED:
                summary['skipped'] += 1
            else:
                summary['failed'] += 1

        return summary
