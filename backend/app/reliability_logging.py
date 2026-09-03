import logging

from fastapi import Request


_LOGGER = logging.getLogger("ludex.reliability")


def log_database_request_failure(request: Request) -> None:
    """Record bounded database diagnostics without exception or request data."""
    route = request.scope.get("route")
    operation = getattr(route, "name", "unknown_route")
    _LOGGER.error(
        "Database request failed.",
        extra={
            "operation": operation,
            "failure_category": "database_unavailable",
            "status_code": 503,
        },
    )
