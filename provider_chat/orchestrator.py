from django.conf import settings
from django.db.models import FloatField, Min, Value
from django.db.models.functions import ACos, Cast, Cos, Greatest, Least, Radians, Sin
from rest_framework.exceptions import ValidationError

from provider_search.serializers import (
    ProviderSearchFilterSerializer,
    ProviderSummarySerializer,
)
from provider_search.services import public_provider_summary_queryset, search_providers

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
        total, providers_with_distance = _nearby_providers(
            filters,
            interpretation.sort,
            user_location,
        )
        providers = [provider for provider, _distance in providers_with_distance]
    else:
        queryset = search_providers(
            filters,
            interpretation.sort,
            queryset=public_provider_summary_queryset(),
        )
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
    """Let the database rank coordinates, then hydrate only the bounded results."""
    latitude = float(user_location["latitude"])
    longitude = float(user_location["longitude"])
    request_latitude = Radians(Value(latitude, output_field=FloatField()))
    request_longitude = Radians(Value(longitude, output_field=FloatField()))
    location_latitude = Radians(Cast("locations__latitude", FloatField()))
    location_longitude = Radians(Cast("locations__longitude", FloatField()))
    cosine_angle = (
        Sin(request_latitude) * Sin(location_latitude)
        + Cos(request_latitude)
        * Cos(location_latitude)
        * Cos(location_longitude - request_longitude)
    )
    clamped_angle = Least(
        Value(1.0),
        Greatest(Value(-1.0), cosine_angle),
    )
    distance_miles = Value(3958.7613) * ACos(clamped_angle)

    ranked_providers = (
        search_providers(
            filters,
            sort,
            queryset=public_provider_summary_queryset(),
        )
        .prefetch_related(None)
        .order_by()
        .filter(
            locations__latitude__isnull=False,
            locations__longitude__isnull=False,
        )
        .annotate(
            distance_miles=Min(
                distance_miles,
                output_field=FloatField(),
            )
        )
        .order_by("distance_miles", "name", "id")
    )
    total = ranked_providers.count()
    selected = list(
        ranked_providers.values_list("id", "distance_miles")[
            : settings.CHAT_MAX_RESULTS
        ]
    )
    selected_ids = [provider_id for provider_id, _distance in selected]
    loaded_providers = {
        provider.id: provider
        for provider in public_provider_summary_queryset().filter(id__in=selected_ids)
    }
    return total, [
        (loaded_providers[provider_id], distance)
        for provider_id, distance in selected
        if provider_id in loaded_providers
    ]


def _validate_search_filters(filters):
    serializer = ProviderSearchFilterSerializer(data=filters)
    try:
        serializer.is_valid(raise_exception=True)
    except ValidationError as exc:
        raise AIResponseError("AI filters failed application validation.") from exc
    return serializer.validated_data


def _provider_detail_response(provider_slug, informational_answer=None):
    provider = public_provider_summary_queryset().filter(slug=provider_slug).first()
    if provider is None:
        return _empty_response(
            intent="provider_details",
            assistant_message=_combine_messages(
                informational_answer,
                "I could not find an active provider with that reference.",
            ),
            provider_slug=provider_slug,
        )

    result = ProviderSummarySerializer(provider).data
    return {
        "intent": "provider_details",
        "assistant_message": _combine_messages(
            informational_answer,
            f"Here are the public details for {provider.name}.",
        ),
        "provider_slug": provider_slug,
        "count": 1,
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
