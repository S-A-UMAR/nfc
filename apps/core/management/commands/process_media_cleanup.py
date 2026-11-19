from django.core.management.base import BaseCommand
from apps.core.services.media_cleanup_service import MediaCleanupService


class Command(BaseCommand):
    help = "Processes pending or failed Cloudinary media cleanup tasks."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of tasks to process in a single batch (default: 50).'
        )
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Include previously failed tasks that have not exceeded max attempts.'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        retry_failed = options['retry_failed']

        self.stdout.write(f"Starting media cleanup processing (limit={limit}, retry_failed={retry_failed})...")
        summary = MediaCleanupService.process_pending_tasks(limit=limit, retry_failed=retry_failed)

        self.stdout.write(
            self.style.SUCCESS(
                f"Media cleanup completed: {summary['processed']} processed "
                f"({summary['completed']} completed, {summary['skipped']} skipped, {summary['failed']} failed)."
            )
        )
