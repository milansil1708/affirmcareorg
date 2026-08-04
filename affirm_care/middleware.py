import logging
from time import perf_counter


logger = logging.getLogger("affirm_care.performance")


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
