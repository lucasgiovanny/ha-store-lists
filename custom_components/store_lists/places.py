"""The one Google Places (New) call this integration needs: what is near a point."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import FIELD_MASK, PLACES_URL
from .logic import Place, parse_places


class PlacesError(Exception):
    """Places answered with an error, or did not answer."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"{status}: {message}" if status else message)
        self.status = status


async def search_nearby(
    session: aiohttp.ClientSession,
    api_key: str,
    latitude: float,
    longitude: float,
    radius: float,
    *,
    types: list[str] | None = None,
    primary_types: list[str] | None = None,
    rank: str = "DISTANCE",
    max_results: int = 20,
    language: str = "en",
) -> list[Place]:
    body: dict[str, Any] = {
        "maxResultCount": max_results,
        "rankPreference": rank,
        "languageCode": language,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius,
            }
        },
    }
    if types:
        body["includedTypes"] = types
    if primary_types:
        body["includedPrimaryTypes"] = primary_types
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}
    try:
        async with session.post(
            PLACES_URL, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            content = await resp.json(content_type=None)
            if resp.status != 200:
                error = (content or {}).get("error", {}) if isinstance(content, dict) else {}
                raise PlacesError(resp.status, error.get("message") or str(content)[:200])
    except (aiohttp.ClientError, TimeoutError) as err:
        raise PlacesError(None, str(err) or type(err).__name__) from err
    return parse_places(content)
