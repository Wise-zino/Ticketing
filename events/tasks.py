"""
Expiry sweeper. NOT required for correctness: reserve_ticket() already treats
an expired hold as available, so a late or crashed sweeper can never cause an
oversell or a stuck ticket. The sweeper exists so that stored ticket rows,
admin views and "tickets_available" counts reflect reality instead of
waiting for someone to try to claim that exact row.

Concurrency: the release is one UPDATE statement. If a reserve_ticket()
transaction has the row locked, Postgres makes the UPDATE wait, then
re-evaluates the WHERE clause against the committed row. A ticket that was
just reclaimed by someone new (fresh reserved_until) no longer matches and is
left alone, so the sweeper can't clobber a live reservation.
"""
from celery import shared_task
from django.utils import timezone

from .models import Ticket

def sweep_expired_reservations():
    """Plain function so it's usable from tests and the management command."""
    now = timezone.now()
    updated = Ticket.objects.filter(
        status=Ticket.Status.RESERVED, reserved_until__lt=now
    ).update(status=Ticket.Status.AVAILABLE, reserved_by=None, reserved_until=None)
    return updated

@shared_task
def sweep_expired_reservations_task():
    """Celery entry point, scheduled by Celery beat (see CELERY_BEAT_SCHEDULE)."""
    return sweep_expired_reservations()
