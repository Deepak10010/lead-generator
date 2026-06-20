"""Tests for the OpenStreetMap/Overpass source (HTTP mocked with respx)."""

import httpx
import pytest
import respx

from app.config import settings
from app.models import SearchRequest
from app.sources.overpass import OverpassSource, osm_filters


def test_known_category_maps_to_tags():
    assert osm_filters("Restaurants") == ['["amenity"="restaurant"]']
    assert osm_filters("dentists") == ['["amenity"="dentist"]', '["healthcare"="dentist"]']
    assert osm_filters("gym") == ['["leisure"="fitness_centre"]']


def test_synonyms_and_plurals():
    assert osm_filters("coffee shops") == ['["amenity"="cafe"]']
    assert osm_filters("  Lawyers ") == ['["office"="lawyer"]']


def test_unknown_category_falls_back_to_fuzzy_keys():
    filters = osm_filters("florist")
    # Falls back to a case-insensitive regex across the common keys.
    assert all("~" in f and "florist" in f for f in filters)
    assert any('["shop"~"florist",i]' == f for f in filters)


def test_fallback_strips_quotes_to_avoid_injection():
    filters = osm_filters('rest"aurant')
    assert all('"aurant' not in f.replace('~"', "").replace('",i', "") for f in filters)


_NOMINATIM = [{"boundingbox": ["12.8", "13.1", "77.4", "77.8"]}]
_OVERPASS = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 12.9,
            "lon": 77.6,
            "tags": {
                "name": "Tasty Corner",
                "amenity": "restaurant",
                "addr:housenumber": "12",
                "addr:street": "MG Road",
                "addr:city": "Bengaluru",
                "website": "https://tasty.example",
                "phone": "+91 80 1234 5678",
            },
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 12.95, "lon": 77.61},
            "tags": {"name": "No Site Diner", "amenity": "restaurant"},
        },
        # Unnamed feature -> dropped.
        {"type": "node", "id": 3, "tags": {"amenity": "restaurant"}},
    ]
}


@respx.mock
async def test_search_parses_elements():
    respx.get(settings.nominatim_url).mock(return_value=httpx.Response(200, json=_NOMINATIM))
    overpass = respx.post(settings.overpass_url).mock(
        return_value=httpx.Response(200, json=_OVERPASS)
    )

    businesses = await OverpassSource().search(
        SearchRequest(city="Bangalore", category="Restaurants")
    )

    assert len(businesses) == 2  # unnamed element dropped
    first = businesses[0]
    assert first.name == "Tasty Corner"
    assert first.website == "https://tasty.example"
    assert first.phone == "+91 80 1234 5678"
    assert first.address == "12 MG Road, Bengaluru"
    assert first.source_id == "node/1"

    # website-less business comes through with website=None (a lead candidate)
    assert businesses[1].name == "No Site Diner"
    assert businesses[1].website is None

    # The Overpass query body carried the restaurant tag filter (form-encoded).
    from urllib.parse import unquote_plus

    sent_body = unquote_plus(overpass.calls.last.request.content.decode())
    assert '["amenity"="restaurant"]' in sent_body
