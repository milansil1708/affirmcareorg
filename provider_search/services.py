from django.conf import settings
from django.core.cache import cache
from django.db.models import F, Prefetch, Q

from provider_organizations.models import (
    AffirmingFeature,
    OrganizationService,
    ProviderFeature,
    ProviderLocation,
    ProviderOrganization,
    Service,
)

from .cache_keys import (
    DIRECTORY_CATALOG_CACHE_KEY,
    FEATURED_PROVIDER_IDS_CACHE_KEY,
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
    """Return every public field and relationship used by the detail API."""
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
        Prefetch(
            "affirming_features",
            queryset=ProviderFeature.objects.select_related("feature").order_by(
                "feature__label", "id"
            ),
        ),
    )


def public_provider_card_queryset():
    """Return only the related data rendered by public provider cards."""
    return _public_provider_list_queryset("phone")


def public_provider_summary_queryset():
    """Return only fields serialized by provider search and chat APIs."""
    return _public_provider_list_queryset()


def _public_provider_list_queryset(*extra_provider_fields):
    provider_fields = ("id", "slug", "name", "org_type", *extra_provider_fields)
    return ProviderOrganization.objects.filter(is_active=True).only(
        *provider_fields
    ).prefetch_related(
        Prefetch(
            "locations",
            queryset=ProviderLocation.objects.only(
                "id",
                "organization_id",
                "city",
                "state_code",
                "is_primary",
            ).order_by("-is_primary", "id"),
        ),
        Prefetch(
            "services", queryset=OrganizationService.objects.select_related(
                "service"
            ).only(
                "id",
                "organization_id",
                "service_id",
                "service__slug",
                "service__name",
            ).order_by("service__name", "id"),
        ),
    )


def get_featured_providers(limit=6):
    """Fetch a short rotating selection without sorting all providers each request."""
    provider_ids = cache.get(FEATURED_PROVIDER_IDS_CACHE_KEY)
    if provider_ids is None:
        provider_ids = list(
            ProviderOrganization.objects.filter(is_active=True)
            .order_by("?")
            .values_list("id", flat=True)[:limit]
        )
        cache.set(
            FEATURED_PROVIDER_IDS_CACHE_KEY,
            provider_ids,
            settings.FEATURED_PROVIDER_CACHE_SECONDS,
        )

    providers_by_id = {
        provider.id: provider
        for provider in public_provider_card_queryset().filter(id__in=provider_ids)
    }
    return [
        providers_by_id[provider_id]
        for provider_id in provider_ids
        if provider_id in providers_by_id
    ]


def get_public_directory_catalog():
    """Return the small, shared filter catalog without re-querying every view."""
    catalog = cache.get(DIRECTORY_CATALOG_CACHE_KEY)
    if catalog is not None:
        return catalog

  catalog = {
    "states": [
        "DC" if state.strip().lower() == "district of columbia" else state
        for state in (
            ProviderLocation.objects.filter(organization__is_active=True)
            .exclude(state_code__in=["", "Virginia"])
            .order_by("state_code")
            .values_list("state_code", flat=True)
            .distinct()
        )
    ],
    "services": list(
        Service.objects.order_by("name").values("slug", "name")
    ),
    "affirming_features": list(
        AffirmingFeature.objects.order_by("label").values(
            "code", "label"
        )
    ),
}
    cache.set(
        DIRECTORY_CATALOG_CACHE_KEY,
        catalog,
        settings.DIRECTORY_CATALOG_CACHE_SECONDS,
    )
    return catalog


def search_providers(filters, sort="name", *, queryset=None):
    providers = queryset if queryset is not None else public_provider_card_queryset()

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
