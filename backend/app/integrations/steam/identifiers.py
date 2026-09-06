from dataclasses import dataclass
import re
from typing import Literal
from urllib.parse import unquote, urlsplit

STEAM_ID_PATTERN = re.compile(r"^\d{17}$")
INVALID_IDENTIFIER_MESSAGE = (
    "Enter a 17-digit Steam ID or a Steam Community profile URL."
)

SteamIdentifierKind = Literal["steam_id", "vanity"]


class InvalidSteamIdentifierError(ValueError):
    """Indicate that a submitted Steam identifier is unsupported."""

    pass


@dataclass(frozen=True)
class SteamIdentifier:
    """Represent a normalized numeric or vanity Steam identifier."""

    kind: SteamIdentifierKind
    value: str


def normalize_steam_identifier(raw_identifier: str) -> SteamIdentifier:
    """Normalize a Steam ID or supported Steam Community profile URL.

    Args:
        raw_identifier: A raw 17-digit ID, numeric profile URL, or vanity URL.

    Returns:
        A normalized identifier labeled as numeric or vanity-based.

    Raises:
        InvalidSteamIdentifierError: If the value is malformed, uses another
            host, or is not a supported Steam Community profile URL.
    """
    candidate = raw_identifier.strip()
    if STEAM_ID_PATTERN.fullmatch(candidate):
        return SteamIdentifier(kind="steam_id", value=candidate)
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
    except ValueError as error:
        raise InvalidSteamIdentifierError(
            INVALID_IDENTIFIER_MESSAGE
        ) from error

    if parsed.scheme not in {"http", "https"} or hostname is None:
        raise InvalidSteamIdentifierError(INVALID_IDENTIFIER_MESSAGE)

    normalized_hostname = hostname.lower()
    if normalized_hostname.startswith("www."):
        normalized_hostname = normalized_hostname[4:]

    if normalized_hostname != "steamcommunity.com":
        raise InvalidSteamIdentifierError(INVALID_IDENTIFIER_MESSAGE)

    path_parts = [
        unquote(part)
        for part in parsed.path.split("/")
        if part
    ]

    if len(path_parts) != 2:
        raise InvalidSteamIdentifierError(INVALID_IDENTIFIER_MESSAGE)

    profile_type, profile_value = path_parts

    if (
        profile_type == "profiles"
        and STEAM_ID_PATTERN.fullmatch(profile_value)
    ):
        return SteamIdentifier(
            kind="steam_id",
            value=profile_value,
        )

    if profile_type == "id":
        vanity_name = profile_value.strip()

        if (
            not vanity_name
            or len(vanity_name) > 100
            or "/" in vanity_name
        ):
            raise InvalidSteamIdentifierError(
                INVALID_IDENTIFIER_MESSAGE
            )

        return SteamIdentifier(
            kind="vanity",
            value=vanity_name,
        )

    raise InvalidSteamIdentifierError(INVALID_IDENTIFIER_MESSAGE)
