from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from events.models import Event, Ticket


class Command(BaseCommand):
    help = "Check inventory invariants for an event (run after a load test)."

    def add_arguments(self, parser):
        parser.add_argument("event_id", type=int)

    def handle(self, *args, **opts):
        try:
            event = Event.objects.get(pk=opts["event_id"])
        except Event.DoesNotExist:
            raise CommandError("No such event.")

        now = timezone.now()
        counts = Ticket.objects.filter(event=event).aggregate(
            total=Count("id"),
            available=Count("id", filter=Q(status=Ticket.Status.AVAILABLE)),
            reserved_active=Count(
                "id",
                filter=Q(status=Ticket.Status.RESERVED, reserved_until__gte=now),
            ),
            reserved_expired=Count(
                "id",
                filter=Q(status=Ticket.Status.RESERVED, reserved_until__lt=now),
            ),
            sold=Count("id", filter=Q(status=Ticket.Status.SOLD)),
        )
        holders = (
            Ticket.objects.filter(event=event, status__in=["reserved", "sold"])
            .values("reserved_by")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .count()
        )

        self.stdout.write(f"Event {event.id}: {event.name}")
        for k, v in counts.items():
            self.stdout.write(f"  {k:17} {v}")
        self.stdout.write(f"  users holding >1  {holders}")

        problems = []
        if counts["total"] != event.total_tickets:
            problems.append("ticket row count differs from event.total_tickets")
        if counts["sold"] > event.total_tickets:
            problems.append("OVERSOLD: sold > total_tickets")
        if (
            counts["available"]
            + counts["reserved_active"]
            + counts["reserved_expired"]
            + counts["sold"]
            != counts["total"]
        ):
            problems.append("status buckets don't add up to total")
        if holders:
            problems.append("a user holds more than one ticket for this event")

        if problems:
            raise CommandError("INVARIANT VIOLATION: " + "; ".join(problems))
        self.stdout.write(self.style.SUCCESS("All inventory invariants hold."))
