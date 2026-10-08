"""Request-level Steam abuse controls shared by the session routes."""

from datetime import UTC, datetime
from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, Request, status

from app.abuse.steam import (
    RateLimitExceeded,
    SteamAbuseController,
    resolve_client_address,
)
from app.config import settings


_STEAM_ABUSE_CONTROLLER = SteamAbuseController()


def get_steam_abuse_controller() -> SteamAbuseController:
    """Provide bounded process-local abuse state and a test seam."""
    return _STEAM_ABUSE_CONTROLLER


def get_steam_abuse_clock() -> datetime:
    """Provide one replaceable UTC clock for request-level controls."""
    return datetime.now(UTC)


def raise_rate_limit(error: RateLimitExceeded) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many Steam requests. Try again later.",
        headers={"Retry-After": str(error.retry_after)},
    ) from error


def enforce_session_attempt_limit(
    request: Request,
    controller: Annotated[
        SteamAbuseController,
        Depends(get_steam_abuse_controller),
    ],
) -> None:
    """Count every session-creation attempt using memory-only client state."""
    try:
        client_address = resolve_client_address(
            deployment_environment=settings.deployment_environment,
            socket_host=(request.client.host if request.client else None),
            forwarded_for=request.headers.get("x-forwarded-for"),
        )
        controller.record_session_attempt(
            client_address,
            now=get_steam_abuse_clock(),
        )
    except (RateLimitExceeded, ValueError) as error:
        if isinstance(error, RateLimitExceeded):
            raise_rate_limit(error)
        raise_rate_limit(RateLimitExceeded(60))
