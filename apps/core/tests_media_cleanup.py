from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import MediaCleanupTask
from apps.core.services.media_cleanup_service import MediaCleanupService
from apps.profiles.models import Profile, ProfileGalleryItem, ProfileTestimonial
from apps.websites.models import Website, Service, Product

User = get_user_model()


class MediaCleanupUnitTests(TestCase):
    """
    Unit tests for MediaCleanupService:
    1. Successful deletion
    2. Idempotency (already deleted / not found)
    3. Failed deletion with diagnostic error tracking
    4. Retry mechanism with max_attempts limit
    5. Duplicate request prevention
    6. Shared asset protection (skips deletion if referenced elsewhere)
    7. Full model coverage (Profile, Gallery, Testimonial, Service, Product)
    8. Exclude deleting user from shared reference check
    9. Recovery of failed tasks via queue retry
    """

    def setUp(self):
        self.user_a = User.objects.create_user(
            email='media_user_a@example.com',
            password='Password123!',
            first_name='Media',
            last_name='UserA'
        )
        self.user_b = User.objects.create_user(
            email='media_user_b@example.com',
            password='Password123!',
            first_name='Media',
            last_name='UserB'
        )
        self.profile_a = self.user_a.profile
        self.profile_a.profile_image = 'profile_photos/user_a_avatar.jpg'
        self.profile_a.cover_image = 'cover_photos/user_a_cover.jpg'
        self.profile_a.business_logo = 'logos/user_a_logo.png'
        self.profile_a.save()

        self.profile_b = self.user_b.profile
        self.profile_b.profile_image = 'profile_photos/user_b_avatar.jpg'
        self.profile_b.save()

    def test_extract_public_id(self):
        """Extracts clean public_id from paths and URLs, ignoring local defaults."""
        self.assertEqual(
            MediaCleanupService.extract_public_id('profile_photos/photo123.jpg'),
            'profile_photos/photo123'
        )
        self.assertEqual(
            MediaCleanupService.extract_public_id('https://res.cloudinary.com/stride/image/upload/v12345/gallery/art1.png'),
            'gallery/art1'
        )
        # Default placeholder returns empty string
        self.assertEqual(MediaCleanupService.extract_public_id('img/default-avatar.png'), '')
        self.assertEqual(MediaCleanupService.extract_public_id(None), '')

    def test_enqueue_user_media(self):
        """Enqueue collects all distinct media assets for a user."""
        tasks = MediaCleanupService.enqueue_user_media(self.user_a)
        self.assertEqual(len(tasks), 3)
        task_pids = {t.public_id for t in tasks}
        self.assertIn('profile_photos/user_a_avatar', task_pids)
        self.assertIn('cover_photos/user_a_cover', task_pids)
        self.assertIn('logos/user_a_logo', task_pids)

    def test_enqueue_all_media_models(self):
        """
        Complete media coverage:
        Confirms Profile avatar, cover image, logo, ProfileGalleryItem,
        ProfileTestimonial, Service, and Product images are all collected.
        """
        # Add Gallery Item and Testimonial to profile_a
        ProfileGalleryItem.objects.create(
            profile=self.profile_a,
            title='Artwork',
            image='profiles/gallery/art_piece1.jpg'
        )
        ProfileTestimonial.objects.create(
            profile=self.profile_a,
            client_name='Satisfied Client',
            client_avatar='profiles/testimonials/client_face.png'
        )

        # Add Website with Service and Product
        website = Website.objects.create(
            user=self.user_a,
            title="User A Website",
            slug="user-a-site"
        )
        Service.objects.create(
            website=website,
            name="Consulting",
            price=1500,
            image="websites/services/consulting_banner.jpg"
        )
        Product.objects.create(
            website=website,
            name="Physical NFC Tag",
            price=3000,
            image="websites/products/nfc_tag_photo.jpg"
        )

        tasks = MediaCleanupService.enqueue_user_media(self.user_a)
        # Expect 7 distinct assets: avatar, cover, logo, gallery, testimonial, service, product
        self.assertEqual(len(tasks), 7)
        task_pids = {t.public_id for t in tasks}
        self.assertIn('profile_photos/user_a_avatar', task_pids)
        self.assertIn('cover_photos/user_a_cover', task_pids)
        self.assertIn('logos/user_a_logo', task_pids)
        self.assertIn('profiles/gallery/art_piece1', task_pids)
        self.assertIn('profiles/testimonials/client_face', task_pids)
        self.assertIn('websites/services/consulting_banner', task_pids)
        self.assertIn('websites/products/nfc_tag_photo', task_pids)

    def test_duplicate_enqueue_prevention(self):
        """Duplicate enqueueing does not create redundant pending tasks."""
        tasks1 = MediaCleanupService.enqueue_user_media(self.user_a)
        self.assertEqual(len(tasks1), 3)
        tasks2 = MediaCleanupService.enqueue_user_media(self.user_a)
        self.assertEqual(len(tasks2), 3)
        # Database only contains 3 tasks, not 6
        self.assertEqual(MediaCleanupTask.objects.count(), 3)

    @patch('cloudinary.uploader.destroy')
    def test_successful_deletion(self, mock_destroy):
        """Successful Cloudinary deletion transitions task to COMPLETED."""
        mock_destroy.return_value = {'result': 'ok'}

        task = MediaCleanupTask.objects.create(
            public_id='test/unique_asset_123',
            status=MediaCleanupTask.STATUS_PENDING
        )

        success = MediaCleanupService.process_task(task)
        self.assertTrue(success)

        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_COMPLETED)
        self.assertEqual(task.attempts, 1)
        self.assertIsNotNone(task.completed_at)
        mock_destroy.assert_called_once_with('test/unique_asset_123', resource_type='image', invalidate=True)

    @patch('cloudinary.uploader.destroy')
    def test_idempotent_already_deleted_handling(self, mock_destroy):
        """Cloudinary returning 'not found' is treated as successful deletion (idempotent)."""
        mock_destroy.return_value = {'result': 'not found'}

        task = MediaCleanupTask.objects.create(
            public_id='test/already_deleted_asset',
            status=MediaCleanupTask.STATUS_PENDING
        )

        success = MediaCleanupService.process_task(task)
        self.assertTrue(success)

        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_COMPLETED)
        self.assertIsNotNone(task.completed_at)

    @patch('cloudinary.uploader.destroy')
    def test_failed_deletion_diagnostic_tracking(self, mock_destroy):
        """Failed Cloudinary requests record attempt count and error diagnostics without disappearing."""
        mock_destroy.side_effect = Exception("Cloudinary connection timeout to api.cloudinary.com")

        task = MediaCleanupTask.objects.create(
            public_id='test/failing_asset',
            status=MediaCleanupTask.STATUS_PENDING
        )

        success = MediaCleanupService.process_task(task)
        self.assertFalse(success)

        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_FAILED)
        self.assertEqual(task.attempts, 1)
        self.assertIn("Cloudinary connection timeout", task.last_error)

    @patch('cloudinary.uploader.destroy')
    def test_retry_mechanism_and_max_attempts(self, mock_destroy):
        """Failed tasks can be retried up to max_attempts, then marked permanently failed."""
        mock_destroy.side_effect = Exception("Temporary 500 error")

        task = MediaCleanupTask.objects.create(
            public_id='test/retry_asset',
            status=MediaCleanupTask.STATUS_FAILED,
            attempts=4,
            max_attempts=5
        )

        # 5th attempt executes
        success = MediaCleanupService.process_task(task)
        self.assertFalse(success)
        task.refresh_from_db()
        self.assertEqual(task.attempts, 5)

        # 6th attempt is blocked by max_attempts guard
        mock_destroy.reset_mock()
        success_after_max = MediaCleanupService.process_task(task)
        self.assertFalse(success_after_max)
        mock_destroy.assert_not_called()
        self.assertIn("Max attempts", task.last_error)

    @patch('cloudinary.uploader.destroy')
    def test_shared_asset_protection(self, mock_destroy):
        """If an asset is still referenced by another profile, deletion is skipped."""
        # Share User A's avatar with User B
        shared_asset_path = 'profile_photos/user_a_avatar.jpg'
        self.profile_b.profile_image = shared_asset_path
        self.profile_b.save()

        task = MediaCleanupTask.objects.create(
            public_id='profile_photos/user_a_avatar',
            status=MediaCleanupTask.STATUS_PENDING
        )

        success = MediaCleanupService.process_task(task)
        self.assertTrue(success)

        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_SKIPPED)
        self.assertIn("still referenced", task.last_error)
        mock_destroy.assert_not_called()

    def test_shared_asset_protection_with_exclude_user(self):
        """
        Confirms that the account being deleted can be excluded from reference check,
        while other users' references are strictly respected.
        """
        pid = 'profile_photos/user_a_avatar'
        # With User A owning the asset:
        # Without exclusion: referenced = True
        self.assertTrue(MediaCleanupService.is_asset_referenced(pid))
        # With User A excluded (and User B NOT referencing it): referenced = False
        self.assertFalse(MediaCleanupService.is_asset_referenced(pid, exclude_user_id=self.user_a.id))

        # Now User B references the asset too:
        self.profile_b.profile_image = 'profile_photos/user_a_avatar.jpg'
        self.profile_b.save()

        # With User A excluded, but User B referencing it: referenced = True
        self.assertTrue(MediaCleanupService.is_asset_referenced(pid, exclude_user_id=self.user_a.id))

    @patch('cloudinary.uploader.destroy')
    def test_recover_failed_tasks_via_queue(self, mock_destroy):
        """
        Verifies that failed deletions remain recoverable through the task queue.
        Initial failure sets STATUS_FAILED; retry_failed=True recovers it once API succeeds.
        """
        # First attempt: failure
        mock_destroy.side_effect = Exception("Temporary Cloudinary 503")
        task = MediaCleanupTask.objects.create(
            public_id='test/recoverable_asset',
            status=MediaCleanupTask.STATUS_PENDING
        )
        summary1 = MediaCleanupService.process_pending_tasks(retry_failed=False)
        self.assertEqual(summary1['failed'], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_FAILED)
        self.assertEqual(task.attempts, 1)

        # Second attempt: Cloudinary is back online; retry_failed=True re-processes it
        mock_destroy.side_effect = None
        mock_destroy.return_value = {'result': 'ok'}

        summary2 = MediaCleanupService.process_pending_tasks(retry_failed=True)
        self.assertEqual(summary2['completed'], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, MediaCleanupTask.STATUS_COMPLETED)
        self.assertEqual(task.attempts, 2)
        self.assertEqual(task.last_error, "")


class MediaCleanupIntegrationTests(TestCase):
    """
    Integration tests for account deletion media cleanup flow.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='delete_media_user@example.com',
            password='SecurePassword123!',
            first_name='Delete',
            last_name='Me'
        )
        self.profile = self.user.profile
        self.profile.profile_image = 'profile_photos/delete_avatar.jpg'
        self.profile.cover_image = 'cover_photos/delete_cover.jpg'
        self.profile.save()

    @patch('cloudinary.uploader.destroy')
    def test_account_deletion_queues_and_cleans_up_media(self, mock_destroy):
        """Deleting an account enqueues media tasks and processes them safely."""
        mock_destroy.return_value = {'result': 'ok'}

        self.client.force_login(self.user)
        response = self.client.post(reverse('dashboard:delete_account'), {
            'confirm_acknowledgment': 'on',
            'confirm_password': 'SecurePassword123!',
        })
        self.assertEqual(response.status_code, 302)

        # User is deleted
        self.assertFalse(User.objects.filter(email='delete_media_user@example.com').exists())

        # Media tasks were created and processed
        tasks = MediaCleanupTask.objects.filter(public_id__in=[
            'profile_photos/delete_avatar',
            'cover_photos/delete_cover'
        ])
        self.assertEqual(tasks.count(), 2)
        for task in tasks:
            self.assertEqual(task.status, MediaCleanupTask.STATUS_COMPLETED)

        self.assertEqual(mock_destroy.call_count, 2)
