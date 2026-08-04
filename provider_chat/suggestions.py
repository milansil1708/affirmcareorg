"""Directory-backed starter searches for the provider chat."""

from django.conf import settings
from django.core.cache import cache

from provider_search.cache_keys import CHAT_SUGGESTIONS_CACHE_KEY
from provider_search.services import search_providers


SUGGESTION_DEFINITIONS = (
    {
        "id": "new-york-providers",
        "label": "Providers in New York",
        "prompt": "Find providers in New York",
        "icon": "fa-location-dot",
        "filters": {"state_code": "NY"},
    },
    {
        "id": "california-providers",
        "label": "Providers in California",
        "prompt": "Find providers in California",
        "icon": "fa-location-dot",
        "filters": {"state_code": "CA"},
    },
    {
        "id": "telehealth-providers",
        "label": "Telehealth providers",
        "prompt": "Find telehealth providers",
        "icon": "fa-laptop-medical",
        "filters": {"delivery_modes": ["telehealth"]},
    },
    {
        "id": "accessible-clinics",
        "label": "Accessible clinics",
        "prompt": "Find wheelchair-accessible clinics",
        "icon": "fa-wheelchair-move",
        "filters": {
            "org_types": ["clinic"],
            "wheelchair_accessible": True,
        },
    },
    {
        "id": "youth-services",
        "label": "Youth services",
        "prompt": "Find providers offering youth services",
        "icon": "fa-people-roof",
        "filters": {"age_groups": ["youth"]},
    },
    {
        "id": "informed-consent",
        "label": "Informed consent",
        "prompt": "Find providers that use informed consent",
        "icon": "fa-shield-heart",
        "filters": {"affirming_feature_codes": ["informed-consent"]},
    },
    {
        "id": "gender-neutral-restrooms",
        "label": "Gender-neutral restrooms",
        "prompt": "Find providers with gender-neutral restrooms",
        "icon": "fa-restroom",
        "filters": {"gender_neutral_restrooms": True},
    },
    {
        "id": "public-transit",
        "label": "Public-transit access",
        "prompt": "Find providers with public-transit access",
        "icon": "fa-train-subway",
        "filters": {"public_transit_access": True},
    },
    {
        "id": "online-booking",
        "label": "Online booking",
        "prompt": "Find providers with online booking",
        "icon": "fa-calendar-check",
        "filters": {"has_booking_url": True},
    },
)


def get_available_suggestions():
    """Return only starter searches that currently produce public results."""
    cached_suggestions = cache.get(CHAT_SUGGESTIONS_CACHE_KEY)
    if cached_suggestions is not None:
        return cached_suggestions

    available = []
    for definition in SUGGESTION_DEFINITIONS:
        if search_providers(definition["filters"]).exists():
            available.append(
                {
                    **definition,
                    "filters": definition["filters"].copy(),
                }
            )
    cache.set(
        CHAT_SUGGESTIONS_CACHE_KEY,
        available,
        settings.CHAT_SUGGESTIONS_CACHE_SECONDS,
    )
    return available
