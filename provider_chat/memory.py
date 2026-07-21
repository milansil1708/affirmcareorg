from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from provider_organizations.models import ProviderOrganization
from provider_search.serializers import ProviderSearchFilterSerializer

from .exceptions import ConversationNotFoundError, ConversationStateError
from .models import ChatConversation, ChatTurn


@dataclass(frozen=True)
class ConversationMemory:
    prompt_context: dict
    history: list[dict]
    allowed_provider_slugs: frozenset[str]
    selected_provider_slug: str | None


def get_or_create_conversation(request, conversation_id=None):
    now = timezone.now()
    ownership = _conversation_ownership(request)

    if conversation_id is None:
        return ChatConversation.objects.create(
            **_conversation_creation_owner(request),
            expires_at=_new_expiry(now),
        )

    conversation = (
        ChatConversation.objects.filter(
            id=conversation_id,
            expires_at__gt=now,
            **ownership,
        )
        .first()
    )
    if conversation is None:
        raise ConversationNotFoundError
    return conversation


def build_conversation_memory(conversation, requested_provider_slug=None):
    current_filters = _validated_stored_filters(conversation.current_filters)
    result_providers = _active_result_providers(
        conversation.result_provider_slugs
    )
    selected_provider_slug = (
        requested_provider_slug or conversation.selected_provider_slug or None
    )

    allowed_slugs = {provider["slug"] for provider in result_providers}
    if selected_provider_slug:
        allowed_slugs.add(selected_provider_slug)

    prompt_context = {
        "current_search": {
            "filters": current_filters,
            "sort": conversation.current_sort,
        },
        "previous_results": result_providers,
        "selected_provider_slug": selected_provider_slug,
        "pending_clarification": conversation.pending_clarification or None,
    }
    return ConversationMemory(
        prompt_context=prompt_context,
        history=_recent_history(conversation),
        allowed_provider_slugs=frozenset(allowed_slugs),
        selected_provider_slug=selected_provider_slug,
    )


@transaction.atomic
def record_successful_turn(conversation, user_message, result):
    intent = result["intent"]
    conversation.expires_at = _new_expiry()

    if intent not in ChatTurn.Intent.values:
        conversation.save(update_fields=("expires_at", "updated_at"))
        return

    if intent in {
        ChatTurn.Intent.SEARCH_PROVIDERS,
        ChatTurn.Intent.CLARIFICATION,
    }:
        conversation.current_filters = _validated_stored_filters(
            result.get("filters", {})
        )
        conversation.current_sort = result.get("sort", "name")
        conversation.pending_clarification = (
            result["assistant_message"]
            if intent == ChatTurn.Intent.CLARIFICATION
            else ""
        )

    if intent == ChatTurn.Intent.SEARCH_PROVIDERS:
        conversation.result_provider_slugs = [
            provider["slug"] for provider in result.get("results", ())
        ]
        conversation.selected_provider_slug = ""
    elif intent == ChatTurn.Intent.PROVIDER_DETAILS:
        conversation.selected_provider_slug = result.get("provider_slug", "")
        conversation.pending_clarification = ""

    conversation.save()
    ChatTurn.objects.create(
        conversation=conversation,
        user_message=user_message,
        assistant_message=result["assistant_message"],
        intent=intent,
    )
    _trim_old_turns(conversation)


def _conversation_ownership(request):
    if request.user.is_authenticated:
        return {"user": request.user}
    return {
        "user__isnull": True,
        "session_key": _ensure_session_key(request),
    }


def _conversation_creation_owner(request):
    if request.user.is_authenticated:
        return {"user": request.user, "session_key": ""}
    return {"user": None, "session_key": _ensure_session_key(request)}


def _ensure_session_key(request):
    if request.session.session_key is None:
        request.session.create()
    return request.session.session_key


def _new_expiry(now=None):
    return (now or timezone.now()) + timedelta(
        minutes=settings.CHAT_CONVERSATION_TTL_MINUTES
    )


def _validated_stored_filters(filters):
    serializer = ProviderSearchFilterSerializer(data=filters)
    if not serializer.is_valid():
        raise ConversationStateError("Stored conversation filters are invalid.")
    return serializer.data


def _active_result_providers(provider_slugs):
    if not isinstance(provider_slugs, list):
        raise ConversationStateError("Stored provider references are invalid.")

    providers = {
        provider["slug"]: provider
        for provider in ProviderOrganization.objects.filter(
            is_active=True,
            slug__in=provider_slugs,
        ).values("slug", "name")
    }
    return [providers[slug] for slug in provider_slugs if slug in providers]


def _recent_history(conversation):
    limit = max(1, settings.CHAT_MEMORY_MAX_TURNS)
    turns = list(
        conversation.turns.order_by("-created_at", "-id")[:limit]
    )
    history = []
    for turn in reversed(turns):
        history.extend(
            (
                {"role": "user", "content": turn.user_message},
                {"role": "assistant", "content": turn.assistant_message},
            )
        )
    return history


def _trim_old_turns(conversation):
    limit = max(1, settings.CHAT_MEMORY_MAX_TURNS)
    retained_ids = list(
        conversation.turns.order_by("-created_at", "-id")
        .values_list("id", flat=True)[:limit]
    )
    conversation.turns.exclude(id__in=retained_ids).delete()

