"""
Mock payment provider behind a small interface. Swapping in a real provider
(Stripe, etc.) later means writing one new class and changing where it's
instantiated in services.py — nothing else in the app needs to know.
"""
import time
import uuid
from dataclasses import dataclass

from .exceptions import PaymentDeclined

@dataclass
class PaymentResult:
    reference: str
    amount_cents: int

class PaymentProvider:
    def charge(self, *, amount_cents, idempotency_key, simulate=None) -> PaymentResult:
        raise NotImplementedError
    
    def refund(self, *, reference: str) -> None:
        raise NotImplementedError
    

class MockPaymentProvider(PaymentProvider):
    """
    `simulate` lets you exercise every branch of the checkout flow on demand
    instead of hoping a flaky test provider decides to fail for you:

        None / "success"  -> charges instantly
        "decline"          -> raises PaymentDeclined, as a real card decline would
        "slow"              -> sleeps 12s (longer than a short reservation window
                                you might use in tests) before succeeding, to
                                exercise the "paid after the hold expired" path
        "error"             -> raises a generic exception, simulating a
                                provider outage / network failure
    """

    SLOW_DELAY_SECONDS = 12

    def charge(self, *, amount_cents, idempotency_key, simulate=None) -> PaymentResult:
        if simulate == "decline":
            raise PaymentDeclined("Mock provider declined the charge.")
        if simulate == "error":
            raise RuntimeError("Mock provider: simulated outage.")
        if simulate == "slow":
            time.sleep(self.SLOW_DELAY_SECONDS)

        return PaymentResult(
            reference=f"mock_{uuid.uuid4().hex}",
            amount_cents=amount_cents,
        )
    
    def refund(self, *, reference: str) -> None:
        # No-op for the mock — a real provider would call its refund API here.
        return None