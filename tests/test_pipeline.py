"""Tests for the end-to-end pipeline using a fake source + mocked HTTP."""

import httpx
import pytest
import respx

from app import pipeline
from app.models import Business, SearchRequest
from app.sources.base import BusinessSource

RESPONSIVE = '<html><head><meta name="viewport" content="width=device-width"></head></html>'
DESKTOP = "<html><head></head><body>old</body></html>"


class FakeSource(BusinessSource):
    name = "fake"

    async def search(self, req):
        return [
            Business(name="Good Cafe", website="https://good.example"),
            Business(name="No Site Diner", website=None),
            Business(name="Down Bistro", website="https://err.example"),
            Business(name="Old Grill", website="https://desktop.example"),
        ]


@pytest.fixture(autouse=True)
def use_fake_source(monkeypatch):
    monkeypatch.setattr(pipeline, "get_source", lambda name=None: FakeSource())


@respx.mock
async def test_pipeline_flags_and_sorts():
    respx.get("https://good.example").mock(return_value=httpx.Response(200, html=RESPONSIVE))
    respx.get("https://err.example").mock(return_value=httpx.Response(500))
    respx.get("https://desktop.example").mock(return_value=httpx.Response(200, html=DESKTOP))

    leads = await pipeline.run(SearchRequest(city="Bangalore", category="Restaurants"))

    by_name = {l.business.name: l for l in leads}
    assert by_name["Good Cafe"].check.status == "ok"
    assert by_name["Good Cafe"].is_lead is False
    assert by_name["No Site Diner"].check.status == "none"
    assert by_name["Down Bistro"].check.status == "broken"
    assert by_name["Old Grill"].check.status == "not_mobile_friendly"

    # Three of four are leads, and leads sort to the front.
    assert sum(1 for l in leads if l.is_lead) == 3
    assert leads[-1].business.name == "Good Cafe"  # the only non-lead is last
    assert all(l.is_lead for l in leads[:3])

    # Flags carry the human-readable label.
    assert by_name["No Site Diner"].flags == ["No website"]
