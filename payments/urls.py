from django.urls import path
from . import views

urlpatterns = [
    path("tickets/<int:pk>/checkout/", views.CheckoutView.as_view(), name="ticket-checkout",),
]
