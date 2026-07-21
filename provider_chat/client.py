import logging

from django.conf import settings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError as PydanticValidationError

from .exceptions import (
    AIConfigurationError,
    AIRefusalError,
    AIResponseError,
    AITemporaryError,
)
from .prompts import build_system_instructions
from .schemas import ChatInterpretation


logger = logging.getLogger(__name__)


def interpret_provider_request(
    message,
    application_provider_slug=None,
    conversation_context=None,
    conversation_history=None,
    has_user_location=False,
):
    if not settings.OPENAI_API_KEY:
        raise AIConfigurationError("The OpenAI API key is not configured.")

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    try:
        prompt_kwargs = {"conversation_context": conversation_context}
        if has_user_location:
            prompt_kwargs["has_user_location"] = True
        response = client.responses.parse(
            model=settings.OPENAI_MODEL,
            instructions=build_system_instructions(
                application_provider_slug,
                **prompt_kwargs,
            ),
            input=_response_input(message, conversation_history),
            text_format=ChatInterpretation,
            max_output_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
            store=False,
        )
    except (AuthenticationError, PermissionDeniedError) as exc:
        logger.error("OpenAI authentication or permission failure: %s", type(exc).__name__)
        raise AIConfigurationError("OpenAI authentication failed.") from exc
    except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as exc:
        logger.warning("Temporary OpenAI failure: %s", type(exc).__name__)
        raise AITemporaryError("OpenAI is temporarily unavailable.") from exc
    except (BadRequestError, PydanticValidationError) as exc:
        logger.error("OpenAI request or structured response failure: %s", type(exc).__name__)
        raise AIResponseError("OpenAI returned an invalid structured response.") from exc
    except APIStatusError as exc:
        logger.error("OpenAI API status failure: %s", exc.status_code)
        raise AIResponseError("OpenAI could not process the request.") from exc
    except OpenAIError as exc:
        logger.error("Unexpected OpenAI SDK failure: %s", type(exc).__name__)
        raise AIResponseError("OpenAI could not process the request.") from exc

    if response.output_parsed is not None:
        return response.output_parsed

    if _response_contains_refusal(response):
        raise AIRefusalError("OpenAI refused the request.")
    raise AIResponseError("OpenAI did not return a structured interpretation.")


def _response_input(message, conversation_history):
    response_input = []
    for item in conversation_history or ():
        if (
            item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
        ):
            raise AIResponseError("Conversation history is invalid.")
        response_input.append(
            {"role": item["role"], "content": item["content"]}
        )
    response_input.append({"role": "user", "content": message})
    return response_input


def _response_contains_refusal(response):
    for output in response.output:
        for content in getattr(output, "content", ()):
            if getattr(content, "type", None) == "refusal":
                return True
    return False
