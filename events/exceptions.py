# Custom Exception types created for clarity

class SoldOut(Exception):
    """
    No available (or expired-reservation) tickets remain for this event.
    """

class AlreadyReserved(Exception):
    """
    This user already holds an active reservation for this event.
    """