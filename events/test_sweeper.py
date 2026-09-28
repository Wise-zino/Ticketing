from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Event, Ticket
from .tasks import sweep_expired_reservations

User = get_user_model()


class SweeperTest(TestCase):
    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.event = Event.objects.create(
            organizer=organizer,
            name="Sweeper Event",
            starts_at=timezone.now(),
            total_tickets=3,
        )
        now = timezone.now()
        self.expired = Ticket.objects.create(
            event=self.event,
            status=Ticket.Status.RESERVED,
            reserved_by=self.buyer,
            reserved_until=now - timedelta(minutes=1),
        )
        self.active = Ticket.objects.create(
            event=self.event,
            status=Ticket.Status.RESERVED,
            reserved_by=self.buyer,
            reserved_until=now + timedelta(minutes=5),
        )
        self.sold = Ticket.objects.create(
            event=self.event,
            status=Ticket.Status.SOLD,
            reserved_by=self.buyer,
            sold_at=now,
        )

    def test_releases_only_expired_reservations(self):
        released = sweep_expired_reservations()
        self.assertEqual(released, 1)

        self.expired.refresh_from_db()
        self.assertEqual(self.expired.status, Ticket.Status.AVAILABLE)
        self.assertIsNone(self.expired.reserved_by)
        self.assertIsNone(self.expired.reserved_until)

        self.active.refresh_from_db()
        self.assertEqual(self.active.status, Ticket.Status.RESERVED)

        self.sold.refresh_from_db()
        self.assertEqual(self.sold.status, Ticket.Status.SOLD)

    def test_is_idempotent(self):
        sweep_expired_reservations()
        self.assertEqual(sweep_expired_reservations(), 0)
