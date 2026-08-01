from django.conf import settings
from rest_framework.exceptions import ValidationError

from provider_search.serializers import (
    ProviderDetailSerializer,
    ProviderSearchFilterSerializer,
    ProviderSummarySerializer,
)
from provider_search.services import public_provider_queryset, search_providers

from . import client as ai_client
from .exceptions import AIResponseError


UNSUPPORTED_MESSAGES = {
    "medical_advice": (
        "I can share general LGBTQ+ health information, but I can't diagnose or "
        "recommend personal treatment."
    ),
    "emergency": (
        "I can't assess emergencies. If you're in immediate danger, contact local "
        "emergency services now."
    ),
    "insurance": "Insurance information is not available in the directory.",
    "ratings_reviews": "Ratings and reviews are not available in the directory.",
    "pricing": "Pricing is not available in the directory.",
    "languages": "Language information is not available in the directory.",
    "availability": (
        "Live availability is not available; use a listed booking link."
    ),
    "database_or_private_data": "I can only use public provider information.",
    "prompt_injection": (
        "I can help with LGBTQ+ health information and providers, but I can't "
        "reveal protected instructions."
    ),
    "out_of_scope": (
        "I can help with LGBTQ+ health information and Affirm Care provider "
        "searches, but not with that request."
    ),
}


def handle_chat_message(
    message,
    application_provider_slug=None,
    conversation_context=None,
    conversation_history=None,
    allowed_provider_slugs=(),
    user_location=None,
):
    interpretation = ai_client.interpret_provider_request(
        message,
        application_provider_slug=application_provider_slug,
        conversation_context=conversation_context,
        conversation_history=conversation_history,
        has_user_location=bool(user_location),
    )
    _validate_interpretation_state(
        interpretation,
        application_provider_slug,
        allowed_provider_slugs,
        user_location=user_location,
    )

    if interpretation.intent == "informational":
        return _empty_response(
            intent="informational",
            assistant_message=interpretation.informational_answer.strip(),
        )

    if interpretation.intent == "clarification":
        filters = _validate_search_filters(
            interpretation.filters.to_search_data()
        )
        response = _empty_response(
            intent="clarification",
            assistant_message=_combine_messages(
                interpretation.informational_answer,
                interpretation.clarification_question,
            ),
            filters=filters,
            sort=interpretation.sort,
        )
        response["_pending_clarification"] = (
            interpretation.clarification_question
        )
        return response

    if interpretation.intent == "unsupported_request":
        return _empty_response(
            intent="unsupported_request",
            assistant_message=UNSUPPORTED_MESSAGES[
                interpretation.unsupported_category
            ],
            unsupported_category=interpretation.unsupported_category,
        )

    if interpretation.intent == "provider_details":
        return _provider_detail_response(
            interpretation.provider_slug,
            informational_answer=interpretation.informational_answer,
        )

    filters = _validate_search_filters(interpretation.filters.to_search_data())
    if user_location:
        providers_with_distance = _nearby_providers(
            filters,
            interpretation.sort,
            user_location,
        )
        total = len(providers_with_distance)
        providers_with_distance = providers_with_distance[: settings.CHAT_MAX_RESULTS]
        providers = [provider for provider, _distance in providers_with_distance]
    else:
        queryset = search_providers(filters, interpretation.sort)
        total = queryset.count()
        providers = list(queryset[: settings.CHAT_MAX_RESULTS])
    results = ProviderSummarySerializer(providers, many=True).data
    if user_location:
        for result, (_provider, distance_miles) in zip(results, providers_with_distance):
            result["distance_miles"] = round(distance_miles, 1)
    return {
        "intent": "search_providers",
        "assistant_message": _combine_messages(
            interpretation.informational_answer,
            (
                _nearby_search_message(total)
                if user_location
                else _search_message(total)
            ),
        ),
        "filters": filters,
        "sort": interpretation.sort,
        "count": total,
        "results_returned": len(results),
        "has_more": total > len(results),
        "results": results,
    }


def _validate_interpretation_state(
    interpretation,
    application_provider_slug,
    allowed_provider_slugs=(),
    user_location=None,
):
    if (
        interpretation.informational_answer is not None
        and not interpretation.informational_answer.strip()
    ):
        raise AIResponseError("Informational answer is empty.")
    if interpretation.intent == "informational":
        if interpretation.informational_answer is None:
            raise AIResponseError("Informational output has no answer.")
        if interpretation.filters.to_search_data():
            raise AIResponseError("Informational output has search filters.")
    elif (
        interpretation.intent == "unsupported_request"
        and interpretation.informational_answer is not None
    ):
        raise AIResponseError(
            "Informational answer conflicts with the unsupported intent."
        )

    if interpretation.intent == "clarification":
        if not interpretation.needs_clarification or not interpretation.clarification_question:
            raise AIResponseError("Clarification output is incomplete.")
    elif interpretation.needs_clarification or interpretation.clarification_question:
        raise AIResponseError("Clarification fields conflict with the intent.")

    if interpretation.intent == "unsupported_request":
        if not interpretation.unsupported_category:
            raise AIResponseError("Unsupported output has no category.")
    elif interpretation.unsupported_category:
        raise AIResponseError("Unsupported category conflicts with the intent.")

    if interpretation.intent == "provider_details" and not interpretation.provider_slug:
        raise AIResponseError("Provider details output has no provider slug.")
    allowed_slugs = set(allowed_provider_slugs)
    if application_provider_slug:
        allowed_slugs.add(application_provider_slug)
    if interpretation.intent == "provider_details":
        if interpretation.provider_slug not in allowed_slugs:
            raise AIResponseError(
                "Provider slug does not match the application context."
            )
    if interpretation.intent != "provider_details" and interpretation.provider_slug:
        raise AIResponseError("Provider slug conflicts with the intent.")

    if (
        interpretation.intent == "search_providers"
        and not interpretation.filters.to_search_data()
        and not user_location
    ):
        raise AIResponseError("Provider search output has no filters.")


def _nearby_providers(filters, sort, user_location):
    """Return matching providers ordered by the distance to their nearest office."""
    latitude = user_location["latitude"]
    longitude = user_location["longitude"]
    providers = search_providers(filters, sort).filter(
        locations__latitude__isnull=False,
        locations__longitude__isnull=False,
    ).distinct()

    nearby = []
    for provider in providers:
        distances = [
            _distance_miles(latitude, longitude, location.latitude, location.longitude)
            for location in provider.locations.all()
            if location.latitude is not None and location.longitude is not None
        ]
        if distances:
            nearby.append((provider, min(distances)))
    return sorted(nearby, key=lambda item: (item[1], item[0].name.lower(), item[0].id))


def _distance_miles(latitude_a, longitude_a, latitude_b, longitude_b):
    """Calculate straight-line distance using the haversine formula."""
    from math import asin, cos, radians, sin, sqrt

    latitude_a, longitude_a, latitude_b, longitude_b = map(
        radians,
        (latitude_a, longitude_a, float(latitude_b), float(longitude_b)),
    )
    latitude_delta = latitude_b - latitude_a
    longitude_delta = longitude_b - longitude_a
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_a) * cos(latitude_b) * sin(longitude_delta / 2) ** 2
    )
    return 3958.7613 * 2 * asin(sqrt(haversine))


def _validate_search_filters(filters):
    serializer = ProviderSearchFilterSerializer(data=filters)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        raise AIResponseError("AI filters failed application validation.") from exc
    return serializer.validated_data


def _provider_detail_response(provider_slug, informational_answer=None):
    provider = public_provider_queryset().filter(slug=provider_slug).first()
    if provider is None:
        return _empty_response(
            intent="provider_details",
            assistant_message=_combine_messages(
                informational_answer,
                "I could not find an active provider with that reference.",
            ),
            provider_slug=provider_slug,
        )

    result = ProviderDetailSerializer(provider).data
    return {
        "intent": "provider_details",
        "assistant_message": _combine_messages(
            informational_answer,
            f"Here are the public details for {provider.name}.",
        ),
        "provider_slug": provider_slug,
        "filters": {},
        "count": 1,
        "results_returned": 1,
        "has_more": False,
        "results": [result],
    }


def _empty_response(
    intent,
    assistant_message,
    filters=None,
    sort=None,
    **extra,
):
    response = {
        "intent": intent,
        "assistant_message": assistant_message,
        "filters": filters or {},
        "count": 0,
        "results_returned": 0,
        "has_more": False,
        "results": [],
        **extra,
    }
    if sort is not None:
        response["sort"] = sort
    return response


def _combine_messages(informational_answer, provider_message):
    if informational_answer is None:
        return provider_message
    return f"{informational_answer.strip()}\n\n{provider_message}"


def _search_message(count):
    if count == 0:
        return "I could not find active providers matching those filters."
    if count == 1:
        return "I found 1 active provider matching your search."
    return f"I found {count} active providers matching your search."


def _nearby_search_message(count):
    if count == 0:
        return "I could not find providers with a mapped location matching your search."
    if count == 1:
        return "I found 1 nearby provider, ordered by distance from your location."
    return f"I found {count} nearby providers, ordered by distance from your location."
