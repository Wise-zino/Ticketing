from django.urls import path
from . import views

urlpatterns = [
    path("events/", views.EventListCreateView.as_view(), name="event-list-create"),
    path("events/<int:pk>/", views.EventDetailView.as_view(), name="event-detail"),
    path("events/<int:pk>/reserve/", views.ReserveTicketView.as_view(), name="event-reserve"),
]
