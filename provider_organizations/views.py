import random
from urllib.parse import quote_plus

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from .models import ProviderLocation, ProviderOrganization


def provider_detail_view(request, slug):
    provider = get_object_or_404(
        ProviderOrganization.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "locations",
                queryset=ProviderLocation.objects.order_by("-is_primary", "id"),
            ),
            Prefetch("services__service"),
        ),
        slug=slug,
    )

    primary_location = provider.locations.first()
    if primary_location:
        if primary_location.latitude and primary_location.longitude:
            map_query = f"{primary_location.latitude},{primary_location.longitude}"
        else:
            full_address = ", ".join(
                filter(
                    None,
                    [
                        primary_location.address_line1,
                        primary_location.address_line2,
                        primary_location.city,
                        primary_location.state_code,
                        primary_location.zip_code,
                    ],
                )
            )
            map_query = full_address
        map_embed_url = f"https://www.google.com/maps?q={quote_plus(map_query)}&output=embed"
    else:
        map_embed_url = None

    provider_service_ids = list(provider.services.values_list("service_id", flat=True))
    similar_queryset = (
        ProviderOrganization.objects.filter(
            is_active=True,
            services__service_id__in=provider_service_ids,
        )
        .exclude(id=provider.id)
        .prefetch_related(
            Prefetch(
                "locations",
                queryset=ProviderLocation.objects.order_by("-is_primary", "id"),
            ),
            Prefetch("services__service"),
        )
        .distinct()
    )
    similar_providers = list(similar_queryset)
    random.shuffle(similar_providers)
    similar_providers = similar_providers[:12]

    offers_telehealth = provider.services.filter(
        delivery_mode__in=["telehealth", "both"]
    ).exists()

    context = {
        "provider": provider,
        "primary_location": primary_location,
        "map_embed_url": map_embed_url,
        "offers_telehealth": offers_telehealth,
        "similar_providers": similar_providers,
    }
    return render(request, "pages/provider_detail.html", context)
