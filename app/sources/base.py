"""The BusinessSource interface and a factory to pick one by name.

Everything downstream (pipeline, UI, export) depends only on this interface,
so adding a real provider means writing one subclass and registering it here —
no other code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import settings
from app.models import Business, SearchRequest


class BusinessSource(ABC):
    """A source that can find businesses for a city + category."""

    name: str = "base"

    @abstractmethod
    async def search(self, req: SearchRequest) -> list[Business]:
        """Return businesses matching the request."""
        raise NotImplementedError


def get_source(name: str | None = None) -> BusinessSource:
    """Return a configured BusinessSource.

    Falls back to the LEAD_SOURCE setting when no name is given.
    """
    # Imported lazily to avoid import cycles and to keep optional deps lazy.
    from app.sources.google_places import GooglePlacesSource
    from app.sources.mock import MockSource
    from app.sources.overpass import OverpassSource

    chosen = (name or settings.lead_source or "mock").lower()
    if chosen == "mock":
        return MockSource()
    if chosen in ("osm", "overpass"):
        return OverpassSource()
    if chosen == "google":
        return GooglePlacesSource(api_key=settings.google_places_api_key)
    raise ValueError(
        f"Unknown LEAD_SOURCE: {chosen!r} (expected 'mock', 'osm', or 'google')"
    )
