from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from .exceptions import PaymentDeclined, ReservationExpired
from events.models import Event, Ticket
from events.services import reserve_ticket
from .models import Payment
from .services import checkout_ticket

User = get_user_model()

class CheckoutTest(TestCase):
    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="x")
        self.buyer = User.objects.create_user(username="buyer", password="x")
        self.event = Event.objects.create(
            organizer=organizer,
            name="Test Event",
            starts_at=timezone.now(),
            total_tickets=1,
            price_cents=2500,
        )
        Ticket.objects.bulk_create([Ticket(event=self.event)])

    def test_happy_path_marks_ticket_sold(self):
        ticket = reserve_ticket(event_id=self.event.id, user=self.buyer)
        result = checkout_ticket(
            ticket_id=ticket.id, user=self.buyer, idempotency_key="key-1"
        )
        result.refresh_from_db()
        self.assertEqual(result.status, Ticket.Status.SOLD)
        self.assertIsNotNone(result.sold_at)
        self.assertIsNone(result.reserved_until)
        self.assertEqual(Payment.objects.get(ticket=result).amount_cents, 2500)

    def test_declined_payment_leaves_ticket_reserved(self):
        ticket = reserve_ticket(event_id=self.event.id, user=self.buyer)
        with self.assertRaises(PaymentDeclined):
            checkout_ticket(ticket_id=ticket.id,
                user=self.buyer,
                idempotency_key="key-2",
                simulate="decline",
            )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.RESERVED)
        self.assertFalse(Payment.objects.filter(ticket=ticket).exists())

    def test_expired_reservation_cannot_be_checked_out(self):
        ticket = reserve_ticket(event_id=self.event.id, user=self.buyer)
        ticket.reserved_until = timezone.now() - timedelta(seconds=1)
        ticket.save(update_fields=["reserved_until"])

        with self.assertRaises(ReservationExpired):
            checkout_ticket(ticket_id=ticket.id, user=self.buyer, idempotency_key="key-3")

    def test_hold_expires_while_payment_is_in_flight(self):
        """
        The classic hard case: the 10-minute hold is set to expire *during*
        a slow payment call. We simulate this with a 1-second reservation
        window and the "slow" provider (12s), so by the time payment
        finishes, checkout_ticket's re-check under lock must catch that the
        reservation is no longer valid, refund, and raise — not sell the
        ticket anyway.
        """
        ticket = reserve_ticket(event_id=self.event.id, user=self.buyer)
        ticket.reserved_until = timezone.now() + timedelta(seconds=1)
        ticket.save(update_fields=["reserved_until"])

        with self.assertRaises(ReservationExpired):
            checkout_ticket(
                ticket_id=ticket.id,
                user=self.buyer,
                idempotency_key="key-4",
                simulate="slow",
            )
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.status, Ticket.Status.SOLD)

    def test_duplicate_idempotency_key_does_not_double_charge(self):
        ticket = reserve_ticket(event_id=self.event.id, user=self.buyer)
        checkout_ticket(ticket_id=ticket.id, user=self.buyer, idempotency_key="key-5")
        # Same key again — must short-circuit, not attempt a second charge
        # against an already-sold ticket.
        result = checkout_ticket(
            ticket_id=ticket.id, user=self.buyer, idempotency_key="key-5"
        )
        self.assertEqual(result.status, Ticket.Status.SOLD)
        self.assertEqual(Payment.objects.filter(ticket=ticket).count(), 1)
