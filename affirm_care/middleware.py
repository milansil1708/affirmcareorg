import logging
from time import perf_counter

from django.conf import settings
from django.http import HttpResponseForbidden


logger = logging.getLogger("affirm_care.performance")


class BlockAbusiveCrawlersMiddleware:
    """Reject known high-volume crawlers before they reach Django views or the DB."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.blocked_user_agents = tuple(
            value.casefold()
            for value in settings.BLOCKED_CRAWLER_USER_AGENTS
            if value.strip()
        )

    def __call__(self, request):
        user_agent = request.headers.get("User-Agent", "").casefold()
        if user_agent and any(
            blocked in user_agent for blocked in self.blocked_user_agents
        ):
            return HttpResponseForbidden("Crawler access denied.\n")
        return self.get_response(request)


class RequestTimingMiddleware:
    """Log slow/error responses without recording query strings or form data."""

    slow_request_threshold_ms = 500

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started_at = perf_counter()
        response = self.get_response(request)
        duration_ms = (perf_counter() - started_at) * 1000

        response["Server-Timing"] = f"app;dur={duration_ms:.1f}"
        if duration_ms >= self.slow_request_threshold_ms or response.status_code >= 500:
            logger.warning(
                "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                request.headers.get("X-Request-ID", "-"),
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
        return response
