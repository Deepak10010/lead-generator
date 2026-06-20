"""Check a single business website and classify it.

Outcomes (see app.models.WebsiteStatus):
  none                -> no URL given
  broken              -> can't load it (connect/DNS/SSL/timeout) or HTTP >= 400
  not_mobile_friendly -> loads, but no usable mobile viewport meta tag
  ok                  -> loads and looks mobile-friendly

Mobile-friendliness is a heuristic: we look for a <meta name="viewport">
containing "width=device-width". Google's old Mobile-Friendly Test API is
deprecated; a future upgrade could call the PageSpeed Insights API for a real
mobile score (see README).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

# A browser-like UA — some sites reject default client UAs with a 403.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 LeadGenerator/0.1"
)

_VIEWPORT_DEVICE_WIDTH = re.compile(r"width\s*=\s*device-width", re.IGNORECASE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def _is_mobile_friendly(html: str) -> bool:
    """True if the page declares a responsive viewport."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("meta"):
        if (tag.get("name") or "").strip().lower() == "viewport":
            content = tag.get("content") or ""
            if _VIEWPORT_DEVICE_WIDTH.search(content):
                return True
    return False


async def check_website(url: str | None, client: httpx.AsyncClient):
    """Classify a website. Returns a WebsiteCheck (imported lazily to avoid cycles)."""
    from app.models import WebsiteCheck

    if not url or not url.strip():
        return WebsiteCheck(status="none", reason="No website listed", checked_at=_now())

    target = _normalize_url(url)
    try:
        resp = await client.get(
            target,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except httpx.TimeoutException:
        return WebsiteCheck(status="broken", reason="Request timed out", checked_at=_now())
    except httpx.HTTPError as exc:
        # Covers ConnectError, DNS failures, SSL errors, too many redirects, etc.
        return WebsiteCheck(
            status="broken",
            reason=f"{type(exc).__name__}: {exc}".strip()[:300],
            checked_at=_now(),
        )

    final_url = str(resp.url)
    if resp.status_code >= 400:
        return WebsiteCheck(
            status="broken",
            http_status=resp.status_code,
            final_url=final_url,
            reason=f"HTTP {resp.status_code}",
            checked_at=_now(),
        )

    if _is_mobile_friendly(resp.text):
        return WebsiteCheck(
            status="ok",
            http_status=resp.status_code,
            final_url=final_url,
            reason="Responsive viewport present",
            checked_at=_now(),
        )

    return WebsiteCheck(
        status="not_mobile_friendly",
        http_status=resp.status_code,
        final_url=final_url,
        reason="No responsive viewport meta tag",
        checked_at=_now(),
    )
