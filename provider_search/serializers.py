from collections.abc import Mapping

from rest_framework import serializers

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)


class StrictSerializer(serializers.Serializer):
    """Reject keys outside the documented public contract."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = sorted(set(data) - set(self.fields))
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field: ["This field is not allowed."]
                        for field in unknown_fields
                    }
                )
        return super().to_internal_value(data)


class ProviderSearchFilterSerializer(StrictSerializer):
    keyword = serializers.CharField(max_length=200, required=False)
    org_types = serializers.ListField(
        child=serializers.ChoiceField(
            choices=ProviderOrganization.ORG_TYPE_CHOICES
        ),
        allow_empty=False,
        max_length=20,
        required=False,
    )
    city = serializers.CharField(max_length=100, required=False)
    state_code = serializers.CharField(max_length=100, required=False)
    zip_code = serializers.CharField(max_length=20, required=False)
    service_slugs = serializers.ListField(
        child=serializers.SlugField(max_length=100),
        allow_empty=False,
        max_length=20,
        required=False,
    )
    delivery_modes = serializers.ListField(
        child=serializers.ChoiceField(
            choices=OrganizationService.DELIVERY_MODE_CHOICES
        ),
        allow_empty=False,
        max_length=20,
        required=False,
    )
    age_groups = serializers.ListField(
        child=serializers.ChoiceField(
            choices=OrganizationService.AGE_GROUP_CHOICES
        ),
        allow_empty=False,
        max_length=20,
        required=False,
    )
    wheelchair_accessible = serializers.BooleanField(required=False)
    gender_neutral_restrooms = serializers.BooleanField(required=False)
    public_transit_access = serializers.BooleanField(required=False)
    affirming_feature_codes = serializers.ListField(
        child=serializers.SlugField(max_length=120),
        allow_empty=False,
        max_length=20,
        required=False,
    )
    verified_after = serializers.DateTimeField(required=False)
    has_booking_url = serializers.BooleanField(required=False)
    has_website_url = serializers.BooleanField(required=False)

    def _validate_unique_list(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Duplicate values are not allowed.")
        return values

    validate_org_types = _validate_unique_list
    validate_delivery_modes = _validate_unique_list
    validate_age_groups = _validate_unique_list

    def validate_state_code(self, value):
        return value.upper()

    def validate_service_slugs(self, values):
        values = self._validate_unique_list(values)
        known = set(
            Service.objects.filter(slug__in=values).values_list("slug", flat=True)
        )
        unknown = sorted(set(values) - known)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown service slug(s): {', '.join(unknown)}."
            )
        return values

    def validate_affirming_feature_codes(self, values):
        values = self._validate_unique_list(values)
        known = set(
            AffirmingFeature.objects.filter(code__in=values).values_list(
                "code", flat=True
            )
        )
        unknown = sorted(set(values) - known)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown affirming feature code(s): {', '.join(unknown)}."
            )
        return values


class ProviderSearchRequestSerializer(StrictSerializer):
    SORT_CHOICES = (
        ("name", "Name (A-Z)"),
        ("-name", "Name (Z-A)"),
        ("last_verified_at", "Oldest verified first"),
        ("-last_verified_at", "Most recently verified first"),
    )

    filters = ProviderSearchFilterSerializer(required=False, default=dict)
    sort = serializers.ChoiceField(
        choices=SORT_CHOICES,
        default="name",
        required=False,
    )


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("slug", "name")


class ProviderLocationSerializer(serializers.ModelSerializer):
    public_transit_access = serializers.BooleanField(
        source="public_transit_notes",
        read_only=True,
    )

    class Meta:
        model = ProviderLocation
        fields = (
            "address_line1",
            "address_line2",
            "city",
            "state_code",
            "zip_code",
            "latitude",
            "longitude",
            "is_primary",
            "wheelchair_accessible",
            "gender_neutral_restrooms",
            "public_transit_access",
        )


class OrganizationServiceSerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)

    class Meta:
        model = OrganizationService
        fields = ("service", "delivery_mode", "age_group", "note")


class ProviderLocationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderLocation
        fields = ("city", "state_code")


class OrganizationServiceSummarySerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)

    class Meta:
        model = OrganizationService
        fields = ("service",)


class AffirmingFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = AffirmingFeature
        fields = ("code", "label", "description")


class ProviderFeatureSerializer(serializers.ModelSerializer):
    feature = AffirmingFeatureSerializer(read_only=True)

    class Meta:
        model = ProviderFeature
        fields = (
            "feature",
            "value",
            "evidence_note",
            "source_url",
            "verified_at",
        )


class ProviderSummarySerializer(serializers.ModelSerializer):
    primary_location = serializers.SerializerMethodField()
    services = OrganizationServiceSummarySerializer(many=True, read_only=True)

    class Meta:
        model = ProviderOrganization
        fields = (
            "slug",
            "name",
            "org_type",
            "primary_location",
            "services",
        )

    def get_primary_location(self, organization):
        locations = list(organization.locations.all())
        if not locations:
            return None
        return ProviderLocationSummarySerializer(locations[0]).data


class ProviderDetailSerializer(serializers.ModelSerializer):
    primary_location = serializers.SerializerMethodField()
    services = OrganizationServiceSerializer(many=True, read_only=True)
    affirming_features = ProviderFeatureSerializer(many=True, read_only=True)
    locations = ProviderLocationSerializer(many=True, read_only=True)

    class Meta:
        model = ProviderOrganization
        fields = (
            "slug",
            "name",
            "org_type",
            "description",
            "website_url",
            "booking_url",
            "phone",
            "email",
            "last_verified_at",
            "primary_location",
            "services",
            "affirming_features",
            "locations",
        )

    def get_primary_location(self, organization):
        locations = list(organization.locations.all())
        if not locations:
            return None
        return ProviderLocationSerializer(locations[0]).data
