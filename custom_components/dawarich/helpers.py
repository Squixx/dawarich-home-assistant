"""Helper functions for the Dawarich integration."""

import logging
from dataclasses import dataclass

import aiohttp
from dawarich_api import DawarichAPI
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

SETTINGS_TIMEOUT = aiohttp.ClientTimeout(total=10)


def get_api(host: str, api_key: str, use_ssl: bool, verify_ssl: bool) -> DawarichAPI:
    """Get the API object."""
    url = host.removeprefix("http://").removeprefix("https://")
    if use_ssl:
        url = f"https://{url}"
    else:
        url = f"http://{url}"
    return DawarichAPI(url=url, api_key=api_key, verify_ssl=verify_ssl)


@dataclass(frozen=True)
class DawarichServerLimits:
    """The server-side settings that constrain how we should send points.

    Both are None when the settings endpoint couldn't be read, in which case
    callers fall back to Dawarich's documented defaults.
    """

    minutes_between_routes: int | None = None
    stay_max_gap_minutes: int | None = None


def _as_int(value: object) -> int | None:
    """Coerce a settings value to int, or None if it isn't numeric."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


async def async_get_server_limits(
    hass: HomeAssistant, api: DawarichAPI
) -> DawarichServerLimits:
    """Read the two track/visit settings we need from the Dawarich server.

    Nothing here is fatal: the tracker works fine without these, they only let
    us tell the user when their idle cadence can't do what they think it does.

    The settings payload also carries unrelated secrets (Immich/Photoprism API
    keys), so only the two keys we need are ever pulled out of it, and the body
    is never logged.
    """
    session = async_get_clientsession(hass, verify_ssl=api.verify_ssl)
    try:
        async with session.get(
            f"{api.url}/api/v1/settings",
            headers={"Authorization": f"Bearer {api.api_key}"},
            timeout=SETTINGS_TIMEOUT,
        ) as response:
            if response.status != 200:
                _LOGGER.debug(
                    "Could not read Dawarich settings (status %s); "
                    "falling back to Dawarich's default track/visit limits",
                    response.status,
                )
                return DawarichServerLimits()
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug(
            "Could not read Dawarich settings (%s); "
            "falling back to Dawarich's default track/visit limits",
            err,
        )
        return DawarichServerLimits()

    settings = payload.get("settings", payload) if isinstance(payload, dict) else {}
    if not isinstance(settings, dict):
        return DawarichServerLimits()

    return DawarichServerLimits(
        minutes_between_routes=_as_int(settings.get("minutes_between_routes")),
        stay_max_gap_minutes=_as_int(settings.get("stay_max_gap_minutes")),
    )
