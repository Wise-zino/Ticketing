from django.db import transaction
from rest_framework import serializers

from .models import Event, Ticket

class EventSerializer(serializers.ModelSerializer):
    organizer = serializers.ReadOnlyField(source="organizer.username")
    tickets_available = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "organizer",
            "name",
            "starts_at",
            "total_tickets",
            "price_cents",
            "tickets_available",
            "created_at",
        ]
        read_only_fields = ["id", "organizer", "created_at"]

    def get_tickets_available(self, obj):
        # This will be cheap because of the (event, status, reserved_until) index
        return obj.tickets.filter(status=Ticket.Status.AVAILABLE).count()
    
    def validate_total_tickets(self, value):
        if value < 1:
            raise serializers.ValidationError("total_tickets must be at least 1.")
        if value > 100_000:
            # Sanity cap — creating the row pool is O(n), see create()
            raise serializers.ValidationError("total_tickets is too large.")
        return value
    
    def create(self, validated_data):
        # creates ticket objects automatically based on the number of tickets set in the event object
        request = self.context["request"]
        with transaction.atomic():
            event = Event.objects.create(organizer=request.user, **validated_data)
            Ticket.objects.bulk_create(
                [Ticket(event=event) for _ in range(event.total_tickets)]
            )
        return event
    

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            "id",
            "event",
            "status",
            "reserved_by",
            "reserved_until",
            "sold_at",
        ]
        read_only_fields = fields