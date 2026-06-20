# Lead Generator

Enter a **city** and **category** (e.g. *Bangalore* / *Restaurants*). The app finds
businesses, checks each one's website, and flags the ones worth approaching:

- **No website** at all
- **Broken website** — down, errors, DNS/SSL failures
- **Not mobile-friendly** — loads, but has no responsive viewport

Results show in a filterable table and download as **CSV** or **Excel**.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (use: source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

copy .env.example .env        # Windows  (use: cp on macOS/Linux)

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000, enter **Bangalore** / **Restaurants**, and hit *Find leads*.
It works immediately with the built-in **mock** source — no API keys needed.

## How it works

```
City + Category
   │
   ▼
BusinessSource.search()   ← pluggable (mock | google | …)
   │  list[Business]
   ▼
check_website()  (async, concurrent)  → none | broken | not_mobile_friendly | ok
   │  list[Lead]
   ▼
Web table  +  CSV / Excel export
```

- `app/sources/` — data sources behind one `BusinessSource` interface.
- `app/checks/website.py` — async website classifier (httpx + BeautifulSoup).
- `app/pipeline.py` — runs the source then checks every site concurrently.
- `app/export.py` — leads → CSV / Excel (pandas + openpyxl).
- `app/main.py` + `app/templates/` — FastAPI web app.

Works for **any category** — restaurants, dentists, gyms, plumbers, salons, etc.
The category box is free text; the data source decides how to interpret it.

## Switching to real data

The mock source ships sample Bangalore restaurants so everything runs offline-free.
Two real sources are available:

### Option A — OpenStreetMap (free, no API key) ✅ recommended to start

```
LEAD_SOURCE=osm
```
That's it — no key, no card. `OverpassSource` geocodes the city (Nominatim) and
queries Overpass for businesses in that area. It maps your category to OSM tags
(`app/sources/overpass.py`, `CATEGORY_TAGS`) — ~40 common verticals are mapped, and
anything unmapped falls back to a fuzzy match so arbitrary categories still work.

*Caveat:* OSM's `website` tag is sparsely filled, so a missing website here means
**"unknown"**, not a guaranteed "no website". Treat OSM no-website results as leads
to verify. Please keep volume modest — the public Overpass/Nominatim servers are free
and shared.

### Option B — Google Places (most complete; paid, has a free credit)

1. In Google Cloud, enable the **Places API** and create an API key.
2. In `.env`:
   ```
   LEAD_SOURCE=google
   GOOGLE_PLACES_API_KEY=your_key_here
   ```
3. Finish `GooglePlacesSource.search()` in `app/sources/google_places.py` (the call
   shape and field mask are already sketched). Its `websiteUri` field is authoritative,
   so the "no website" flag is trustworthy.

Any other provider (SerpApi, Outscraper, Foursquare) is added the same way: write a
`BusinessSource` subclass and register it in `app/sources/base.py`. Nothing else
changes — pipeline, UI, and export are source-agnostic.

## Mobile-friendliness note

We use a heuristic: a page is "mobile-friendly" if it declares
`<meta name="viewport" content="…width=device-width…">`. Google's old
Mobile-Friendly Test API is deprecated; for a real mobile score, plug the
[PageSpeed Insights API](https://developers.google.com/speed/docs/insights/v5/get-started)
into `app/checks/website.py`.

## Tests

```bash
pytest
```

Covers the website classifier (no-url / responsive / desktop-only / 5xx / connect
error / timeout) and the pipeline's flagging + lead-first sorting, with HTTP mocked
via `respx` (no network needed).
