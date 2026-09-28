from django.core.management.base import BaseCommand
from events.tasks import sweep_expired_reservations

class Command(BaseCommand):
    help = "Return expired ticket reservations to the available pool."

    def handle(self, *args, **options):
        count = sweep_expired_reservations()
        self.stdout.write(self.style.SUCCESS(f"Released {count} expired reservation(s)."))