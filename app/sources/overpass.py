"""OpenStreetMap data source via the Overpass API. Free, no API key.

Flow:
  1. Geocode the city to a bounding box with Nominatim.
  2. Map the user's free-text category to OSM tags (e.g. "restaurants" ->
     amenity=restaurant). Unmapped categories fall back to a fuzzy regex match
     across the common OSM keys, so arbitrary verticals still return results.
  3. Query Overpass for matching nodes/ways/relations inside the bbox.
  4. Convert each element to a Business.

Caveats (documented in the README): OSM's `website` tag is sparsely filled, so
a missing website here means "unknown", not a guaranteed "no website". Treat
OSM "no website" results as leads to verify. Be polite to the free public
servers — keep volume modest and send a real User-Agent.
"""

from __future__ import annotations

import re

import httpx

from app.config import settings
from app.models import Business, SearchRequest
from app.sources.base import BusinessSource

USER_AGENT = "LeadGenerator/0.1 (https://example.com; lead-gen demo)"

# Fallback Overpass endpoints, tried in order after the configured primary when
# it returns an error or times out. Public mirrors with global coverage.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Canonical category -> list of OSM (key, value) tag filters.
# Keys are singular; the normalizer strips a trailing "s" before lookup.
CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee shop": [("amenity", "cafe")],
    "bar": [("amenity", "bar"), ("amenity", "pub")],
    "pub": [("amenity", "pub"), ("amenity", "bar")],
    "fast food": [("amenity", "fast_food")],
    "bakery": [("shop", "bakery")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "doctor": [("amenity", "doctors"), ("amenity", "clinic")],
    "clinic": [("amenity", "clinic")],
    "hospital": [("amenity", "hospital")],
    "pharmacy": [("amenity", "pharmacy")],
    "chemist": [("amenity", "pharmacy"), ("shop", "chemist")],
    "gym": [("leisure", "fitness_centre")],
    "fitness": [("leisure", "fitness_centre")],
    "spa": [("leisure", "spa")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "hairdresser": [("shop", "hairdresser")],
    "beauty parlour": [("shop", "beauty")],
    "school": [("amenity", "school")],
    "college": [("amenity", "college")],
    "supermarket": [("shop", "supermarket")],
    "grocery": [("shop", "supermarket"), ("shop", "convenience")],
    "clothing": [("shop", "clothes")],
    "electronics": [("shop", "electronics")],
    "mobile shop": [("shop", "mobile_phone")],
    "jewellery": [("shop", "jewelry")],
    "car repair": [("shop", "car_repair")],
    "car dealer": [("shop", "car")],
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "carpenter": [("craft", "carpenter")],
    "lawyer": [("office", "lawyer")],
    "real estate": [("office", "estate_agent")],
    "bank": [("amenity", "bank")],
    "atm": [("amenity", "atm")],
    "petrol pump": [("amenity", "fuel")],
    "gas station": [("amenity", "fuel")],
    "veterinary": [("amenity", "veterinary")],
    "library": [("amenity", "library")],
    "cinema": [("amenity", "cinema")],
    # Education / classes / coaching (common lead targets).
    "music school": [("amenity", "music_school")],
    "dance school": [("amenity", "dancing_school"), ("leisure", "dance")],
    "driving school": [("amenity", "driving_school")],
    "language school": [("amenity", "language_school")],
    "coaching": [("amenity", "prep_school")],
    "tuition": [("amenity", "prep_school")],
    "kindergarten": [("amenity", "kindergarten")],
    "university": [("amenity", "university")],
    "yoga": [("leisure", "fitness_centre"), ("sport", "yoga")],
}

# Synonyms -> a canonical key already present in CATEGORY_TAGS.
SYNONYMS: dict[str, str] = {
    "restaurants": "restaurant",
    "cafes": "cafe",
    "coffee": "cafe",
    "coffee shops": "cafe",
    "bars": "bar",
    "pubs": "pub",
    "hotels": "hotel",
    "dentists": "dentist",
    "doctors": "doctor",
    "clinics": "clinic",
    "hospitals": "hospital",
    "pharmacies": "pharmacy",
    "gyms": "gym",
    "salons": "salon",
    "saloon": "salon",
    "beauty salon": "salon",
    "schools": "school",
    "supermarkets": "supermarket",
    "groceries": "grocery",
    "grocery store": "grocery",
    "clothes": "clothing",
    "apparel": "clothing",
    "plumbers": "plumber",
    "electricians": "electrician",
    "lawyers": "lawyer",
    "advocate": "lawyer",
    "banks": "bank",
    # Education / classes phrasings.
    "music classes": "music school",
    "music lessons": "music school",
    "music academy": "music school",
    "dance classes": "dance school",
    "dance academy": "dance school",
    "dancing classes": "dance school",
    "driving classes": "driving school",
    "driving lessons": "driving school",
    "language classes": "language school",
    "coaching classes": "coaching",
    "coaching center": "coaching",
    "coaching centre": "coaching",
    "tuition classes": "tuition",
    "tuition center": "tuition",
    "yoga classes": "yoga",
    "yoga studio": "yoga",
}

# Keys searched in the fuzzy fallback for unmapped categories.
_FALLBACK_KEYS = ["amenity", "shop", "craft", "office", "leisure", "tourism", "healthcare", "sport"]

# Generic words that carry no OSM meaning — dropped so the keyword survives,
# e.g. "music classes" -> "music", "car wash service" -> "car wash".
_STOPWORDS = {
    "class", "classes", "lesson", "lessons", "course", "courses", "training",
    "tuition", "coaching", "tutorial", "tutorials", "center", "centre", "centers",
    "centres", "shop", "shops", "store", "stores", "service", "services",
    "institute", "academy", "school", "schools", "studio", "studios", "company",
    "business", "businesses", "near", "me", "in", "the", "and", "of", "for",
}


def osm_filters(category: str) -> list[str]:
    """Return Overpass tag-filter snippets like '["amenity"="restaurant"]'.

    Known categories map to curated tags; unknown ones fall back to a
    case-insensitive regex over common keys so any vertical still matches.
    """
    norm = " ".join(category.strip().lower().split())
    norm = SYNONYMS.get(norm, norm)

    tags = CATEGORY_TAGS.get(norm)
    if tags is None and norm.endswith("s"):
        tags = CATEGORY_TAGS.get(norm[:-1])

    if tags:
        return [f'["{k}"="{v}"]' for k, v in tags]

    # Fallback: pull the meaningful keyword(s) and fuzzy-match them across the
    # common keys. OSM values use underscores (e.g. music_school), so we match
    # individual words rather than the raw phrase, and drop generic filler words.
    words = [w for w in re.split(r"[^a-z0-9]+", norm) if w]
    keywords = [w for w in words if w not in _STOPWORDS] or words
    # Loosely singularize each token (matches "bakers" -> "baker", etc.).
    tokens = {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in keywords}
    pattern = "|".join(sorted(tokens))  # tokens are [a-z0-9] only, regex-safe
    return [f'["{key}"~"{pattern}",i]' for key in _FALLBACK_KEYS]


def _build_query(filters: list[str], bbox: tuple[float, float, float, float], limit: int) -> str:
    south, west, north, east = bbox
    bbox_str = f"({south},{west},{north},{east})"
    parts = "\n  ".join(f"nwr{f}{bbox_str};" for f in filters)
    return f"[out:json][timeout:25];\n(\n  {parts}\n);\nout center tags {limit};"


def _address(tags: dict) -> str:
    parts: list[str] = []
    hn, st = tags.get("addr:housenumber"), tags.get("addr:street")
    if hn and st:
        parts.append(f"{hn} {st}")
    elif st:
        parts.append(st)
    for key in ("addr:suburb", "addr:city", "addr:postcode"):
        val = tags.get(key)
        if val:
            parts.append(val)
    return ", ".join(parts)


def _to_business(element: dict) -> Business | None:
    tags = element.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None  # unnamed OSM features aren't useful leads
    center = element.get("center") or {}
    return Business(
        name=name,
        address=_address(tags),
        phone=tags.get("phone") or tags.get("contact:phone") or tags.get("mobile"),
        website=tags.get("website") or tags.get("contact:website"),
        source_id=f"{element.get('type', 'node')}/{element.get('id', '')}",
        lat=element.get("lat") or center.get("lat"),
        lng=element.get("lon") or center.get("lon"),
    )


class OverpassSource(BusinessSource):
    name = "osm"

    async def _geocode(self, client: httpx.AsyncClient, city: str) -> tuple[float, float, float, float]:
        resp = await client.get(
            settings.nominatim_url,
            params={"q": city, "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"Could not geocode city: {city!r}")
        # Nominatim boundingbox is [south, north, west, east] as strings.
        s, n, w, e = (float(x) for x in results[0]["boundingbox"])
        return (s, w, n, e)

    def _endpoints(self) -> list[str]:
        # Primary first, then mirrors. The public servers intermittently return
        # 406/429 or time out when busy, so we fail over to a mirror.
        endpoints = [settings.overpass_url]
        for mirror in OVERPASS_MIRRORS:
            if mirror not in endpoints:
                endpoints.append(mirror)
        return endpoints

    async def _query_overpass(self, client: httpx.AsyncClient, query: str) -> list[dict]:
        last_error: Exception | None = None
        for url in self._endpoints():
            try:
                # Overpass expects the query in a form field named "data".
                resp = await client.post(
                    url, data={"data": query}, headers={"User-Agent": USER_AGENT}
                )
                resp.raise_for_status()
                return resp.json().get("elements", [])
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc  # try the next mirror
        raise RuntimeError(f"All Overpass endpoints failed; last error: {last_error}")

    async def search(self, req: SearchRequest) -> list[Business]:
        filters = osm_filters(req.category)
        async with httpx.AsyncClient(timeout=40) as client:
            bbox = await self._geocode(client, req.city)
            query = _build_query(filters, bbox, req.limit)
            elements = await self._query_overpass(client, query)

        businesses = [b for b in (_to_business(el) for el in elements) if b]
        return businesses[: req.limit]
