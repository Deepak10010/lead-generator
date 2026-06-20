"""Orchestrates a search: find businesses -> check websites -> build leads."""

from __future__ import annotations

import asyncio

import httpx

from app.checks.website import check_website
from app.config import settings
from app.models import Lead, SearchRequest
from app.sources import get_source


def _lead_sort_key(lead: Lead) -> tuple[int, str]:
    # Leads first; within a group, sort by name for stable display.
    return (0 if lead.is_lead else 1, lead.business.name.lower())


async def run(req: SearchRequest, source_name: str | None = None) -> list[Lead]:
    """Run the full pipeline and return leads (flagged businesses first)."""
    source = get_source(source_name)
    businesses = await source.search(req)

    timeout = httpx.Timeout(settings.website_check_timeout)
    async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
        checks = await asyncio.gather(
            *(check_website(b.website, client) for b in businesses)
        )

    leads = [Lead(business=b, check=c) for b, c in zip(businesses, checks)]
    leads.sort(key=_lead_sort_key)
    return leads
