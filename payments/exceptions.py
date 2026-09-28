class SoldOut(Exception):
    """No available (or expired-reservation) tickets remain for this event."""


class AlreadyReserved(Exception):
    """This user already holds an active reservation for this event."""


class ReservationExpired(Exception):
    """The hold on this ticket lapsed (or belongs to someone else) before payment finished."""


class PaymentDeclined(Exception):
    """The payment provider declined the charge."""
