from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Event
from .serializers import EventSerializer, TicketSerializer
from .exceptions import AlreadyReserved, SoldOut
from .services import reserve_ticket

class IsOrganizerOrReadOnly(permissions.BasePermission):
    """Anyone can view events; only the organizer can act on their own event."""

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.organizer_id == request.user.id
    

class EventListCreateView(generics.ListCreateAPIView):
    queryset = Event.objects.all().order_by("-created_at")
    serializer_class = EventSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]
    

class EventDetailView(generics.RetrieveAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]


class ReserveTicketView(APIView):
    """POST /api/events/<id>/reserve/ — claim one ticket for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            ticket = reserve_ticket(event_id=pk, user=request.user)
        except SoldOut:
            return Response(
                {"detail": "Sold out. All tickets are currently reserved or sold."},
                status=status.HTTP_409_CONFLICT,
            )
        except AlreadyReserved:
            return Response(
                {"detail": "You already have an active reservation for this event."},
                status=status.HTTP_409_CONFLICT,
            )
         
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)
