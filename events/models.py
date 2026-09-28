from django.db import models
from django.conf import settings
from django.db.models import Q


class Event(models.Model):
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organized_events",
    )
    name = models.CharField(max_length=200) # name of event
    starts_at = models.DateTimeField() # when event starts
    total_tickets = models.PositiveIntegerField() # total tickets for the event
    price_cents = models.PositiveIntegerField(default=0) # ticket price (in cent)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

class Ticket(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        SOLD = "sold", "Sold"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="tickets"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.AVAILABLE
    )
    # Holder while reserved, buyer once sold.
    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    reserved_until = models.DateTimeField(null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            # Powers the "find me an available ticket" query in the reserve path.
            models.Index(
                fields=["event", "status", "reserved_until"],
                name="ticket_reserve_lookup_idx",
            ),
        ]
        constraints = [
            # Database-level safety net: even a bug in app code can't
            # persist an impossible ticket state.
            models.CheckConstraint(
                name="ticket_valid_state",
                condition=(
                    Q(
                        status="available",
                        reserved_by__isnull=True,
                        reserved_until__isnull=True,
                    )
                    | Q(
                        status="reserved",
                        reserved_by__isnull=False,
                        reserved_until__isnull=False,
                    )
                    | Q(status="sold", reserved_by__isnull=False)
                ),
            ),
        ]

    def __str__(self):
        return f"Ticket {self.pk} ({self.status}) for event ({self.event.name})"
