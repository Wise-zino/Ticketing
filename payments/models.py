from django.conf import settings
from django.db import models
from events.models import Ticket


class Payment(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        REFUNDED = "refunded", "Refunded"

    ticket = models.OneToOneField(
        Ticket, on_delete=models.CASCADE, related_name="payment"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Client supplies this (e.g. generated once per checkout attempt on the
    # frontend). A unique constraint makes retried checkout requests safe:
    # a duplicate request with the same key can never charge twice.
    idempotency_key = models.CharField(max_length=64, unique=True)
    amount_cents = models.PositiveIntegerField()
    provider_reference = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.pk} for ticket {self.ticket_id} ({self.status})"
