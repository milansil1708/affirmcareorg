from django.conf import settings
from rest_framework import serializers

from provider_search.serializers import StrictSerializer


class ChatRequestSerializer(StrictSerializer):
    message = serializers.CharField(
        max_length=settings.CHAT_MAX_MESSAGE_LENGTH,
        trim_whitespace=True,
    )
    provider_slug = serializers.SlugField(
        max_length=255,
        required=False,
        allow_null=True,
    )
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    latitude = serializers.FloatField(
        required=False,
        min_value=-90,
        max_value=90,
    )
    longitude = serializers.FloatField(
        required=False,
        min_value=-180,
        max_value=180,
    )

    def validate(self, attrs):
        has_latitude = "latitude" in attrs
        has_longitude = "longitude" in attrs
        if has_latitude != has_longitude:
            raise serializers.ValidationError(
                "Latitude and longitude must be provided together."
            )
        return attrs
