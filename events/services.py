from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .exceptions import AlreadyReserved, SoldOut
from .models import Ticket

RESERVATION_MINUTES = 10 # how long a ticket can stay reserved before entering back into the pool
MAX_ACTIVE_RESERVATIONS_PER_USER_PER_EVENT = 1 # how many reserved ticket can be held by a single user

@transaction.atomic
def reserve_ticket(event_id, user):
    """
    Atomically claim one ticket for `user` on `event_id`.

    Concurrency strategy:
    - SELECT ... FOR UPDATE SKIP LOCKED lets N simultaneous requests each grab
      a *different* (ticket) row and proceed in parallel, instead of queueing behind
      a single lock (which is what plain FOR UPDATE, or a counter += 1
      update, would do).
    - The WHERE clause treats a reservation whose 10-minute window has
      passed as fair game. This means correctness never depends on a
      background sweeper running on time — the sweeper (see tasks.py) only
      exists to tidy up data/metrics, not to enforce the rule.
    - The whole function is one transaction, so a crash mid-way rolls back
      to a consistent state (transaction.atomic decorator); no ticket is left half-claimed.
    """
    now = timezone.now()

    # One active hold per user per event keeps a single user (or a buggy
    # retrying client) from locking up the whole pool.
    already_held = (
        Ticket.objects.filter(
            event_id=event_id,
            status=Ticket.Status.RESERVED,
            reserved_by=user,
            reserved_until__gte=now,
        ).exists()
    )
    if already_held:
        raise AlreadyReserved()
    
    ticket = (
        Ticket.objects.select_for_update(skip_locked=True)
        .filter(event_id=event_id)
        .filter(
            Q(status=Ticket.Status.AVAILABLE)
            | Q(status=Ticket.Status.RESERVED, reserved_until__lt=now)
        )
        .order_by("id")
        .first()
    )

    if ticket is None:
        # Note: with SKIP LOCKED, a ticket that's mid-reservation by another
        # concurrent request is invisible to us. It's possible that request
        # rolls back a moment later and the ticket becomes free again — so
        # this "sold out" can occasionally be a false negative. See the
        # README note on retry semantics.
        raise SoldOut()
    
    ticket.status = Ticket.Status.RESERVED
    ticket.reserved_by = user
    ticket.reserved_until = now + timedelta(minutes=RESERVATION_MINUTES)
    ticket.save(update_fields=["status", "reserved_by", "reserved_until"])
    return ticket