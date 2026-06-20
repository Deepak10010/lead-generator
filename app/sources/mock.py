"""A zero-config sample source.

Returns a curated list of plausible Bangalore restaurants whose website fields
deliberately exercise every check outcome:

  * real responsive sites      -> "ok"
  * website=None               -> "none"
  * dead / erroring URLs        -> "broken"
  * a page with no viewport tag -> "not_mobile_friendly"

The URLs point at real public endpoints (python.org, httpstat.us, example.com,
a non-resolving host) so the checks return genuine results over the network.
"""

from __future__ import annotations

from app.models import Business, SearchRequest
from app.sources.base import BusinessSource

# (name, address, phone, website)
_SAMPLE: list[tuple[str, str, str | None, str | None]] = [
    # --- has a proper, mobile-friendly site (viewport present) -> ok ---
    ("Truffles Ice & Spice", "St. Marks Road, Bangalore", "+91 80 4112 0000", "https://www.python.org"),
    ("Vidyarthi Bhavan", "Gandhi Bazaar, Basavanagudi, Bangalore", "+91 80 2667 0000", "https://www.wikipedia.org"),
    ("Toit Brewpub", "100 Feet Road, Indiranagar, Bangalore", "+91 80 4938 0000", "https://www.djangoproject.com"),
    # --- no website at all -> none (prime lead) ---
    ("Brahmin's Coffee Bar", "Shankarapuram, Basavanagudi, Bangalore", "+91 98860 00000", None),
    ("CTR (Shri Sagar)", "Margosa Road, Malleshwaram, Bangalore", "+91 80 2331 0000", None),
    ("Veena Stores", "Margosa Road, Malleshwaram, Bangalore", None, None),
    ("New Modern Hotel", "Jayanagar 4th Block, Bangalore", "+91 80 2654 0000", None),
    # --- broken / unreachable websites -> broken (prime lead) ---
    ("Mavalli Tiffin Room", "Lalbagh Road, Bangalore", "+91 80 2222 0000", "https://httpstat.us/500"),
    ("Koshy's Restaurant", "St. Marks Road, Bangalore", "+91 80 2221 0000", "https://httpstat.us/503"),
    ("Empire Restaurant", "Church Street, Bangalore", "+91 80 4112 1111", "https://httpstat.us/404"),
    ("Hotel Janatha", "Jayanagar, Bangalore", None, "https://no-such-host-lead-gen-demo-xyz.invalid"),
    # --- desktop-only sites, no viewport meta -> not_mobile_friendly (lead).
    # These are stable, genuinely non-responsive pages (the world's first
    # website, etc.) so the heuristic returns a real result over the network.
    ("Airlines Hotel", "Lavelle Road, Bangalore", "+91 80 2221 2222", "http://info.cern.ch"),
    ("Shanti Sagar", "Residency Road, Bangalore", "+91 80 4112 3333", "http://info.cern.ch/hypertext/WWW/TheProject.html"),
    ("Maiya's", "Jayanagar 4th Block, Bangalore", "+91 80 2663 0000", "https://httpbin.org/html"),
    # --- a couple more ok ones to round out the list ---
    ("The Only Place", "Museum Road, Bangalore", "+91 80 2559 0000", "https://www.mozilla.org"),
    ("Nagarjuna", "Residency Road, Bangalore", "+91 80 2558 0000", "https://flask.palletsprojects.com"),
]


class MockSource(BusinessSource):
    name = "mock"

    async def search(self, req: SearchRequest) -> list[Business]:
        businesses = [
            Business(
                name=name,
                address=address,
                phone=phone,
                website=website,
                source_id=f"mock-{i}",
            )
            for i, (name, address, phone, website) in enumerate(_SAMPLE)
        ]
        return businesses[: req.limit]
