from django.db.models import F, Prefetch, Q

from provider_organizations.models import (
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
)


SORT_EXPRESSIONS = {
    "name": ("name", "id"),
    "-name": ("-name", "id"),
    "last_verified_at": (
        F("last_verified_at").asc(nulls_last=True),
        "name",
        "id",
    ),
    "-last_verified_at": (
        F("last_verified_at").desc(nulls_last=True),
        "name",
        "id",
    ),
}


def public_provider_queryset():
    return public_provider_card_queryset().prefetch_related(
        Prefetch(
            "affirming_features",
            queryset=ProviderFeature.objects.select_related("feature").order_by(
                "feature__label", "id"
            ),
        ),
    )


def public_provider_card_queryset():
    """Return only the related data rendered by public provider cards."""
    return ProviderOrganization.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "locations",
            queryset=ProviderLocation.objects.order_by("-is_primary", "id"),
        ),
        Prefetch(
            "services",
            queryset=OrganizationService.objects.select_related("service").order_by(
                "service__name", "id"
            ),
        ),
    )


def search_providers(filters, sort="name"):
    providers = public_provider_queryset()

    keyword = filters.get("keyword")
    if keyword:
        providers = providers.filter(
            Q(name__icontains=keyword)
            | Q(description__icontains=keyword)
            | Q(services__service__name__icontains=keyword)
            | Q(affirming_features__feature__label__icontains=keyword)
        )

    if org_types := filters.get("org_types"):
        providers = providers.filter(org_type__in=org_types)

    location_query = Q()
    has_location_filter = False
    location_mappings = (
        ("city", "locations__city__iexact"),
        ("state_code", "locations__state_code__iexact"),
        ("zip_code", "locations__zip_code__iexact"),
        ("wheelchair_accessible", "locations__wheelchair_accessible"),
        ("gender_neutral_restrooms", "locations__gender_neutral_restrooms"),
        ("public_transit_access", "locations__public_transit_notes"),
    )
    for public_name, model_lookup in location_mappings:
        if public_name in filters:
            location_query &= Q(**{model_lookup: filters[public_name]})
            has_location_filter = True
    if has_location_filter:
        providers = providers.filter(location_query)

    service_query = Q()
    has_service_filter = False
    service_mappings = (
        ("service_slugs", "services__service__slug__in"),
        ("delivery_modes", "services__delivery_mode__in"),
        ("age_groups", "services__age_group__in"),
    )
    for public_name, model_lookup in service_mappings:
        if public_name in filters:
            service_query &= Q(**{model_lookup: filters[public_name]})
            has_service_filter = True
    if has_service_filter:
        providers = providers.filter(service_query)

    # Every requested affirming feature must have an affirmative provider record.
    for feature_code in filters.get("affirming_feature_codes", ()):
        providers = providers.filter(
            affirming_features__feature__code=feature_code,
            affirming_features__value="yes",
        )

    if verified_after := filters.get("verified_after"):
        providers = providers.filter(last_verified_at__gte=verified_after)

    if "has_booking_url" in filters:
        providers = _filter_present_url(
            providers,
            "booking_url",
            filters["has_booking_url"],
        )
    if "has_website_url" in filters:
        providers = _filter_present_url(
            providers,
            "website_url",
            filters["has_website_url"],
        )

    return providers.distinct().order_by(*SORT_EXPRESSIONS[sort])


def _filter_present_url(queryset, field_name, should_exist):
    present = Q(**{f"{field_name}__isnull": False}) & ~Q(**{field_name: ""})
    if should_exist:
        return queryset.filter(present)
    return queryset.filter(~present)
