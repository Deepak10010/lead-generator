"""Google Places data source — skeleton for going live.

Not active by default. To enable:
  1. Create a Google Cloud project, enable the **Places API**, and make an API key.
  2. Put it in .env:  LEAD_SOURCE=google  and  GOOGLE_PLACES_API_KEY=...
  3. Fill in `search()` below (the Text Search call already sketches the shape).

Flow (Places API v1):
  - POST https://places.googleapis.com/v1/places:searchText
      body: {"textQuery": "<category> in <city>"}
      header X-Goog-FieldMask selects the fields we want, e.g.
      "places.displayName,places.formattedAddress,places.nationalPhoneNumber,
       places.websiteUri,places.id,places.location"
  - The response already includes websiteUri, so no separate Place Details
    call is needed for our purposes. Paginate via nextPageToken until `limit`.

Billing: Text Search is a paid SKU (Google gives a recurring free credit).
Keep `limit` modest while testing.
"""

from __future__ import annotations

import httpx

from app.models import Business, SearchRequest
from app.sources.base import BusinessSource

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = (
    "places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
    "places.websiteUri,places.id,places.location"
)


class GooglePlacesSource(BusinessSource):
    name = "google"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "GOOGLE_PLACES_API_KEY is not set. Add it to .env or use LEAD_SOURCE=mock."
            )
        self.api_key = api_key

    async def search(self, req: SearchRequest) -> list[Business]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        body = {"textQuery": f"{req.category} in {req.city}"}

        businesses: list[Business] = []
        async with httpx.AsyncClient(timeout=20) as client:
            # NOTE: pagination via nextPageToken is omitted for brevity; the first
            # page (up to 20 results) is returned. Extend here as needed.
            resp = await client.post(_SEARCH_URL, headers=headers, json=body)
            resp.raise_for_status()
            for place in resp.json().get("places", []):
                loc = place.get("location", {})
                businesses.append(
                    Business(
                        name=(place.get("displayName") or {}).get("text", "Unknown"),
                        address=place.get("formattedAddress", ""),
                        phone=place.get("nationalPhoneNumber"),
                        website=place.get("websiteUri"),
                        source_id=place.get("id", ""),
                        lat=loc.get("latitude"),
                        lng=loc.get("longitude"),
                    )
                )
        return businesses[: req.limit]
