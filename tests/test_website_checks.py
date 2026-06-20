"""Tests for the website classifier, using respx to mock HTTP."""

import httpx
import pytest
import respx

from app.checks.website import check_website

RESPONSIVE_HTML = (
    '<html><head><meta name="viewport" content="width=device-width, '
    'initial-scale=1"></head><body>Hi</body></html>'
)
DESKTOP_ONLY_HTML = "<html><head><title>Old site</title></head><body>Hi</body></html>"


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as c:
        yield c


async def test_no_url_is_none(client):
    result = await check_website(None, client)
    assert result.status == "none"

    result = await check_website("   ", client)
    assert result.status == "none"


@respx.mock
async def test_responsive_site_is_ok(client):
    respx.get("https://good.example").mock(
        return_value=httpx.Response(200, html=RESPONSIVE_HTML)
    )
    result = await check_website("https://good.example", client)
    assert result.status == "ok"
    assert result.http_status == 200


@respx.mock
async def test_no_viewport_is_not_mobile_friendly(client):
    respx.get("https://desktop.example").mock(
        return_value=httpx.Response(200, html=DESKTOP_ONLY_HTML)
    )
    result = await check_website("https://desktop.example", client)
    assert result.status == "not_mobile_friendly"


@respx.mock
async def test_server_error_is_broken(client):
    respx.get("https://err.example").mock(return_value=httpx.Response(500))
    result = await check_website("https://err.example", client)
    assert result.status == "broken"
    assert result.http_status == 500


@respx.mock
async def test_connect_error_is_broken(client):
    respx.get("https://dead.example").mock(
        side_effect=httpx.ConnectError("name resolution failed")
    )
    result = await check_website("https://dead.example", client)
    assert result.status == "broken"


@respx.mock
async def test_timeout_is_broken(client):
    respx.get("https://slow.example").mock(side_effect=httpx.ReadTimeout("too slow"))
    result = await check_website("https://slow.example", client)
    assert result.status == "broken"
    assert "timed out" in result.reason.lower()


@respx.mock
async def test_bare_domain_gets_https_scheme(client):
    route = respx.get("https://nodomain.example").mock(
        return_value=httpx.Response(200, html=RESPONSIVE_HTML)
    )
    result = await check_website("nodomain.example", client)
    assert route.called
    assert result.status == "ok"
