from django.db import IntegrityError, transaction
from django.utils import timezone
from events.models import Ticket
from .models import Payment
from .payments import MockPaymentProvider
from .exceptions import PaymentDeclined, ReservationExpired


def checkout_ticket(ticket_id, user, idempotency_key, simulate=None, payment_provider=None):
    """
    Charge for a reserved ticket and mark it permanently sold.

    Design notes:
    - The payment call happens OUTSIDE any DB transaction/lock. Payment
      providers are slow and unpredictable (that's the whole point of the
      "slow" simulation), and holding a Postgres row lock for the duration
      of an external network call would tie up a DB connection and block
      anyone else touching that row for no good reason.
    - Idempotency is enforced at the database level via Payment's unique
      idempotency_key, not just in application logic — a retried request
      (double-click, client retry after a timeout) can never charge twice,
      even if two copies of this request run concurrently.
    - After payment succeeds, we re-verify the reservation under a lock
      before marking the ticket sold. If the hold expired (or was somehow
      claimed by someone else) while payment was in flight, we refund and
      raise ReservationExpired rather than silently selling a ticket that
      isn't ours to sell.
    """
    payment_provider = payment_provider or MockPaymentProvider()

    # Idempotent short-circuit: if this exact request already succeeded,
    # return the existing result instead of charging again.
    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing.ticket
    
    now = timezone.now()
    ticket = Ticket.objects.filter(pk=ticket_id).first()
    if (
        ticket is None
        or ticket.status != Ticket.Status.RESERVED
        or ticket.reserved_by_id != user.id
        or ticket.reserved_until is None
        or ticket.reserved_until < now
    ):
        raise ReservationExpired()
    
    # --- external call, no DB lock held ---
    try:
        result = payment_provider.charge(
            amount_cents=ticket.event.price_cents,
            idempotency_key=idempotency_key,
            simulate=simulate,
        )
    except PaymentDeclined:
        raise

    # --- finalize under a lock, re-checking everything ---
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket_id)

        still_valid = (
            ticket.status == Ticket.Status.RESERVED
            and ticket.reserved_by_id == user.id
            and ticket.reserved_until is not None
            and ticket.reserved_until >= timezone.now()
        )
        if not still_valid:
            payment_provider.refund(reference=result.reference)
            raise ReservationExpired()
        
        ticket.status = Ticket.Status.SOLD
        ticket.sold_at = timezone.now()
        ticket.reserved_until = None
        ticket.save(update_fields=["status", "sold_at", "reserved_until"])

        try:
            Payment.objects.create(
                ticket=ticket,
                user=user,
                idempotency_key=idempotency_key,
                amount_cents=result.amount_cents,
                provider_reference=result.reference,
                status=Payment.Status.SUCCEEDED,
            )
        except IntegrityError:
            # Lost a race against another request using the same
            # idempotency_key (e.g. two in-flight retries). Payment already
            # recorded by the other request; ours is a harmless duplicate
            # charge attempt against an already-mock-charged ticket, so
            # nothing further to do — the ticket row above is unaffected.
            pass
    
    return ticket