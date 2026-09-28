from rest_framework import serializers

class CheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=64)
    # Demo-only knob so you can trigger every branch by hand / in tests
    # without waiting on a real payment provider to misbehave. This simulte
    # field is used solely for testing should be strip or gated in a prod
    # setting
    simulate = serializers.ChoiceField(
        choices=["success", "decline", "slow", "error"],
        required=False,
        default="success",
    )