"""Turn a list of leads into CSV or Excel bytes for download."""

from __future__ import annotations

import io

import pandas as pd

from app.models import Lead

COLUMNS = [
    "name",
    "address",
    "phone",
    "website",
    "status",
    "flags",
    "is_lead",
    "http_status",
    "reason",
    "checked_at",
]


def _to_dataframe(leads: list[Lead]) -> pd.DataFrame:
    rows = []
    for lead in leads:
        b, c = lead.business, lead.check
        rows.append(
            {
                "name": b.name,
                "address": b.address,
                "phone": b.phone or "",
                "website": b.website or "",
                "status": c.label,
                "flags": ", ".join(lead.flags),
                "is_lead": lead.is_lead,
                "http_status": c.http_status if c.http_status is not None else "",
                "reason": c.reason,
                "checked_at": c.checked_at.isoformat() if c.checked_at else "",
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


def to_csv(leads: list[Lead]) -> bytes:
    return _to_dataframe(leads).to_csv(index=False).encode("utf-8-sig")


def to_excel(leads: list[Lead]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _to_dataframe(leads).to_excel(writer, index=False, sheet_name="Leads")
    return buffer.getvalue()
