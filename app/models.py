"""Pydantic data models shared across the app."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Website check outcomes. Everything except "ok" makes a business a lead.
WebsiteStatus = Literal["ok", "none", "broken", "not_mobile_friendly"]

# Human-readable label per status, used in the UI and exports.
STATUS_LABELS: dict[str, str] = {
    "ok": "OK",
    "none": "No website",
    "broken": "Broken website",
    "not_mobile_friendly": "Not mobile-friendly",
}


class SearchRequest(BaseModel):
    city: str
    category: str
    limit: int = Field(default=60, ge=1, le=200)


class Business(BaseModel):
    """A business as returned by a data source (before website checking)."""

    name: str
    address: str = ""
    phone: Optional[str] = None
    website: Optional[str] = None
    source_id: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None


class WebsiteCheck(BaseModel):
    """Result of checking a single business website."""

    status: WebsiteStatus
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    reason: str = ""
    checked_at: Optional[datetime] = None

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


class Lead(BaseModel):
    """A business plus the result of its website check."""

    business: Business
    check: WebsiteCheck

    @property
    def is_lead(self) -> bool:
        return self.check.status != "ok"

    @property
    def flags(self) -> list[str]:
        if self.check.status == "ok":
            return []
        return [STATUS_LABELS[self.check.status]]
