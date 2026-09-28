"""
Thundering-herd load test: every simulated user fires ONE purchase attempt as
soon as it spawns. Spawn them all at once (-r equal to -u) to approximate
hundreds of people hitting "buy" in the same instant.

Setup:  python manage.py seed_load_test --users 500 --tickets 50
Run:    locust -f loadtest/locustfile.py --headless -u 500 -r 500 -t 60s --host http://localhost:8000 --csv loadtest/results
Verify: python manage.py verify_inventory <event_id>
"""
import json
import os
import random
import uuid

from locust import HttpUser, constant, task

TOKENS_FILE = os.environ.get("TOKENS_FILE", "loadtest/tokens.json")
CHECKOUT_PATH = "/api/tickets/{ticket_id}/checkout/"
CHECKOUT_PROBABILITY = 0.7  # the rest "abandon" and leave a live hold behind

with open(TOKENS_FILE) as f:
    _data = json.load(f)
EVENT_ID = _data["event_id"]
_TOKENS = _data["tokens"]
_next = 0  # Locust runs users as greenlets on one thread, so this is safe


def _claim_token():
    global _next
    token = _TOKENS[_next % len(_TOKENS)]
    _next += 1
    return token


class Buyer(HttpUser):
    wait_time = constant(0)

    def on_start(self):
        self.client.headers["Authorization"] = f"Token {_claim_token()}"

    @task
    def attempt_purchase(self):
        with self.client.post(
            f"/api/events/{EVENT_ID}/reserve/", name="reserve", catch_response=True
        ) as resp:
            if resp.status_code == 201:
                ticket_id = resp.json()["id"]
                resp.success()
            elif resp.status_code == 409:
                # Sold out is an expected, correct outcome for most users.
                resp.success()
                self.stop()
                return
            else:
                resp.failure(f"unexpected status {resp.status_code}")
                self.stop()
                return

        if random.random() < CHECKOUT_PROBABILITY:
            with self.client.post(
                CHECKOUT_PATH.format(ticket_id=ticket_id),
                json={"idempotency_key": uuid.uuid4().hex, "simulate": "success"},
                name="checkout",
                catch_response=True,
            ) as resp:
                if resp.status_code == 200:
                    resp.success()
                else:
                    resp.failure(f"unexpected status {resp.status_code}")
        self.stop()
