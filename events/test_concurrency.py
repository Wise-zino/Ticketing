"""
The Concurrency Test: fire far more simultaneous reservation attempts than
there are tickets, and assert the pool can't be oversold.

Must use TransactionTestCase, not TestCase. TestCase wraps each test in a
transaction and rolls it back at the end, which means every thread would
see the same uncommitted transaction — it would hide the exact race
condition we're trying to prove doesn't exist. TransactionTestCase commits
for real and truncates between tests, so each thread gets a genuine,
separate database connection.
"""
import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from .exceptions import AlreadyReserved, SoldOut
from .models import Event, Ticket
from events.services import reserve_ticket

User = get_user_model()

TOTAL_TICKETS = 50
NUM_CONTENDERS = 200

class ReserveTicketConcurrencyTest(TransactionTestCase):
    # Prevents Django from resetting auto-increment sequences between tests
    # in this class, which is unnecessary here and slightly slower.
    reset_sequences = False

    def setUp(self):
        organizer = User.objects.create_user(username="organizer", password="x")
        self.event = Event.objects.create(
            organizer=organizer,
            name="Concurrency Test Event",
            starts_at=timezone.now(),
            total_tickets=TOTAL_TICKETS,
        )
        Ticket.objects.bulk_create(
            [Ticket(event=self.event) for _ in range(TOTAL_TICKETS)]
        )
        self.users = [
            User.objects.create_user(username=f"buyer{i}", password="x")
            for i in range(NUM_CONTENDERS)
        ]

    def test_cannot_oversell_under_concurrent_load(self):
        results = {"reserved": 0, "sold_out": 0, "errors": []}
        lock = threading.Lock()

        def attempt(user):
            try:
                reserve_ticket(event_id=self.event.id, user=user)
                with lock:
                    results["reserved"] += 1
            except SoldOut:
                with lock:
                    results["sold_out"] += 1
            except AlreadyReserved:
                # Shouldn't happen though because each thread uses a distinct user — but
                # counted separately rather than silently folded into
                # "errors" in case it ever does.
                with lock:
                    results["errors"].append("unexpected AlreadyReserved")
            except Exception as exc:
                with lock:
                    results["errors"].append(repr(exc))
            finally:
                # Each thread gets its own DB connection under Django's
                # thread-local connection handling; close it explicitly so
                # connections don't leak across the 200 threads.
                connection.close()

        threads = [
            threading.Thread(target=attempt, args=(user,)) for user in self.users
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            results["errors"], [], f"Unexpected errors during reservation: {results['errors']}"
        )
        self.assertEqual(results["reserved"], TOTAL_TICKETS)
        self.assertEqual(results["sold_out"], NUM_CONTENDERS - TOTAL_TICKETS)

        # The real proof: no ticket was handed to two different users, and
        # exactly TOTAL_TICKETS tickets ended up reserved
        reserved_tickets = Ticket.objects.filter(event=self.event, status=Ticket.Status.RESERVED)
        self.assertEqual(reserved_tickets.count(), TOTAL_TICKETS)

        holder_ids = list(reserved_tickets.values_list("reserved_by_id", flat=True))
        self.assertEqual(
            len(holder_ids), len(set(holder_ids)), "A ticket was double-reserved to one user or duplicated."
        )

    def test_expired_reservation_can_be_reclaimed(self):
        from datetime import timedelta

        buyer_a, buyer_b = self.users[0], self.users[1]

        # Reserve all tickets, then force one reservation into the past to
        # simulate a checkout that never completed.
        for user in self.users[:TOTAL_TICKETS]:
            reserve_ticket(event_id=self.event.id, user=user)

        expired_ticket = Ticket.objects.filter(
            event=self.event, reserved_by=buyer_a
        ).first()
        expired_ticket.reserved_until = timezone.now() - timedelta(minutes=1)
        expired_ticket.save(update_fields=["reserved_until"])

        # Pool is nominally full, but one hold is expired, so a brand-new
        # contender should still be able to claim it.
        newcomer = User.objects.create_user(username="latecomer", password="x")
        ticket = reserve_ticket(event_id=self.event.id, user=newcomer)

        self.assertEqual(ticket.id, expired_ticket.id)
        self.assertEqual(ticket.reserved_by_id, newcomer.id)
