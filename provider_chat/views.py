from django.conf import settings
from rest_framework import permissions, status
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from django.views.generic import TemplateView

from .exceptions import (
    AIConfigurationError,
    AIRefusalError,
    AIResponseError,
    AITemporaryError,
    ConversationNotFoundError,
    ConversationStateError,
)
from .memory import (
    build_conversation_memory,
    get_or_create_conversation,
    record_successful_turn,
)
from .orchestrator import handle_chat_message
from .serializers import ChatRequestSerializer


class ProviderChatView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "provider_chat"

    def post(self, request):
        request_serializer = ChatRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        validated_data = request_serializer.validated_data

        try:
            conversation = get_or_create_conversation(
                request,
                validated_data.get("conversation_id"),
            )
            memory = build_conversation_memory(
                conversation,
                requested_provider_slug=validated_data.get("provider_slug"),
            )
        except ConversationNotFoundError:
            return _error_response(
                "conversation_not_found",
                "The conversation was not found or has expired.",
                status.HTTP_404_NOT_FOUND,
            )
        except ConversationStateError:
            return _error_response(
                "conversation_invalid",
                "The conversation could not be continued safely.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            result = handle_chat_message(
                validated_data["message"],
                application_provider_slug=memory.selected_provider_slug,
                conversation_context=memory.prompt_context,
                conversation_history=memory.history,
                allowed_provider_slugs=memory.allowed_provider_slugs,
                user_location=(
                    {
                        "latitude": validated_data["latitude"],
                        "longitude": validated_data["longitude"],
                    }
                    if "latitude" in validated_data
                    else None
                ),
            )
        except AIRefusalError:
            result = {
                "intent": "unsupported_request",
                "assistant_message": "I cannot help with that request.",
                "unsupported_category": "out_of_scope",
                "filters": {},
                "count": 0,
                "results_returned": 0,
                "has_more": False,
                "results": [],
            }
        except AIConfigurationError:
            return _error_response(
                "ai_not_configured",
                "The assistant is not configured. Provider search is still available.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AITemporaryError:
            return _error_response(
                "ai_unavailable",
                "The assistant is temporarily unavailable. Provider search is still available.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except AIResponseError:
            return _error_response(
                "ai_invalid_response",
                "The assistant could not understand the request safely. Please try again.",
                status.HTTP_502_BAD_GATEWAY,
            )

        try:
            record_successful_turn(
                conversation,
                validated_data["message"],
                result,
            )
        except ConversationStateError:
            return _error_response(
                "conversation_invalid",
                "The conversation could not be saved safely.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result["conversation_id"] = str(conversation.id)
        return Response(result, status=status.HTTP_200_OK)


class ProviderChatPageView(TemplateView):
    template_name = "provider_chat/chat.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chat_conversation_ttl_ms"] = (
            settings.CHAT_CONVERSATION_TTL_MINUTES * 60 * 1000
        )
        return context


def _error_response(code, message, response_status):
    return Response(
        {"error": {"code": code, "message": message}},
        status=response_status,
    )
