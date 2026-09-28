from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from events.serializers import TicketSerializer
from .serializers import CheckoutSerializer
from .exceptions import PaymentDeclined, ReservationExpired
from .services import checkout_ticket

class CheckoutView(APIView):
    """
    POST /api/tickets/<id>/checkout/ — pay for a reserved ticket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        body = CheckoutSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        try:
            ticket = checkout_ticket(
                ticket_id=pk,
                user=request.user,
                idempotency_key=body.validated_data["idempotency_key"],
                simulate=body.validated_data.get("simulate"),
            )
        except ReservationExpired:
            return Response(
                {"detail": "Your reservation expired or is no longer valid. Please try reserving again."},
                status=status.HTTP_410_GONE,
            )
        except PaymentDeclined:
            return Response(
                {"detail": "Payment was declined."}, status=status.HTTP_402_PAYMENT_REQUIRED
            )
        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)