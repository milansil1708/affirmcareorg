"""Starter prompts for the Affirm Care healthcare assistant."""

from django.conf import settings
from django.core.cache import cache

from provider_search.cache_keys import CHAT_SUGGESTIONS_CACHE_KEY
from provider_search.services import search_providers


SUGGESTION_DEFINITIONS = (
    {
        "id": "affirming-provider",
        "label": "Find an affirming provider",
        "prompt": "Find an LGBTQ+ affirming healthcare provider",
        "icon": "fa-user-doctor",
        "filters": {},
    },
    {
        "id": "providers-near-me",
        "label": "Find providers near me",
        "prompt": "Find LGBTQ+ affirming healthcare providers near me",
        "icon": "fa-location-dot",
        "filters": {},
    },
    {
        "id": "what-is-hrt",
        "label": "What is HRT?",
        "prompt": "What is HRT?",
        "icon": "fa-circle-question",
        "filters": {},
    },
    {
        "id": "gender-affirming-care",
        "label": "How does gender-affirming care work?",
        "prompt": "How does gender-affirming care work?",
        "icon": "fa-heart-pulse",
        "filters": {},
    },
    {
        "id": "healthcare-options",
        "label": "What healthcare options are available?",
        "prompt": "What healthcare options are available for LGBTQ+ people?",
        "icon": "fa-notes-medical",
        "filters": {},
    },
    {
        "id": "insurance",
        "label": "Does insurance cover gender-affirming care?",
        "prompt": "Does insurance cover gender-affirming care?",
        "icon": "fa-file-medical",
        "filters": {},
    },
    {
        "id": "care-cost",
        "label": "How much does gender-affirming care cost?",
        "prompt": "How much does gender-affirming care cost?",
        "icon": "fa-dollar-sign",
        "filters": {},
    },
    {
        "id": "prepare-for-visit",
        "label": "What should I know before seeing a provider?",
        "prompt": "What should I know before seeing an LGBTQ+ affirming healthcare provider?",
        "icon": "fa-clipboard-check",
        "filters": {},
    },
)


def get_available_suggestions():
    """Return starter prompts for the healthcare assistant."""

    cached_suggestions = cache.get(CHAT_SUGGESTIONS_CACHE_KEY)
    if cached_suggestions is not None:
        return cached_suggestions

    available = []

    for definition in SUGGESTION_DEFINITIONS:
        # Informational questions do not require a provider-directory result.
        if not definition["filters"]:
            available.append(
                {
                    **definition,
                    "filters": definition["filters"].copy(),
                }
            )
            continue

        # Provider searches should only appear when they have public results.
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
