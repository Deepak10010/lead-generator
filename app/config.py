"""Application settings, loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Which business data source to use: "mock", "osm", or "google".
    lead_source: str = "mock"

    # Required only when lead_source == "google".
    google_places_api_key: str = ""

    # OpenStreetMap endpoints (used when lead_source == "osm"). No key needed.
    # Overridable so you can point at a mirror if the public servers are busy.
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"

    # Per-request timeout (seconds) when checking a website.
    website_check_timeout: float = 10.0


settings = Settings()
