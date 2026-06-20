"""FastAPI web app: search form, results table, CSV/Excel downloads."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import export
from app.config import settings
from app.models import SearchRequest
from app.pipeline import run as run_pipeline

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Lead Generator")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# In-memory cache of recent searches so exports don't re-run the pipeline.
# Keyed by a short search id. Fine for a single-process prototype.
_RESULTS: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"leads": None, "source": settings.lead_source},
    )


@app.post("/search", response_class=HTMLResponse)
async def search(request: Request, city: str = Form(...), category: str = Form(...)):
    req = SearchRequest(city=city.strip(), category=category.strip())
    leads = await run_pipeline(req)

    search_id = uuid.uuid4().hex[:12]
    _RESULTS[search_id] = {"city": req.city, "category": req.category, "leads": leads}

    lead_count = sum(1 for l in leads if l.is_lead)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "leads": leads,
            "search_id": search_id,
            "city": req.city,
            "category": req.category,
            "total": len(leads),
            "lead_count": lead_count,
            "source": settings.lead_source,
        },
    )


def _get_leads(search_id: str):
    entry = _RESULTS.get(search_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Search expired or not found. Run it again.")
    return entry


@app.get("/export/{search_id}.csv")
async def export_csv(search_id: str):
    entry = _get_leads(search_id)
    data = export.to_csv(entry["leads"])
    filename = f"leads-{search_id}.csv"
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/{search_id}.xlsx")
async def export_xlsx(search_id: str):
    entry = _get_leads(search_id)
    data = export.to_excel(entry["leads"])
    filename = f"leads-{search_id}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
