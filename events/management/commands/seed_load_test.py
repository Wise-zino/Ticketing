import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework.authtoken.models import Token

from events.models import Event, Ticket

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create N buyer accounts (with API tokens) and a fresh event for the "
        "Locust load test. Writes tokens + event id to a JSON file."
    )

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=500)
        parser.add_argument("--tickets", type=int, default=50)
        parser.add_argument("--price-cents", type=int, default=2500)
        parser.add_argument("--output", default="loadtest/tokens.json")

    def handle(self, *args, **opts):
        n_users, n_tickets = opts["users"], opts["tickets"]

        organizer, _ = User.objects.get_or_create(username="loadtest_organizer")

        # Unusable passwords + bulk_create: hashing 500 real passwords would
        # take a minute for no benefit, since load-test users auth by token.
        usernames = [f"loadtest_user_{i}" for i in range(n_users)]
        existing = set(
            User.objects.filter(username__in=usernames).values_list("username", flat=True)
        )
        User.objects.bulk_create(
            [
                User(username=u, password=make_password(None))
                for u in usernames
                if u not in existing
            ]
        )
        users = list(User.objects.filter(username__in=usernames).order_by("username"))

        have_token = set(
            Token.objects.filter(user__in=users).values_list("user_id", flat=True)
        )
        Token.objects.bulk_create(
            [Token(user=u, key=Token.generate_key()) for u in users if u.id not in have_token]
        )
        tokens = list(
            Token.objects.filter(user__in=users).values_list("key", flat=True)
        )

        event = Event.objects.create(
            organizer=organizer,
            name="Load Test Event",
            starts_at=timezone.now() + timedelta(days=30),
            total_tickets=n_tickets,
            price_cents=opts["price_cents"],
        )
        Ticket.objects.bulk_create([Ticket(event=event) for _ in range(n_tickets)])

        out = Path(opts["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"event_id": event.id, "tokens": tokens}))

        self.stdout.write(
            self.style.SUCCESS(
                f"Event {event.id} with {n_tickets} tickets; "
                f"{len(tokens)} buyer tokens written to {out}"
            )
        )
