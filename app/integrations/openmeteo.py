"""
openmeteo.py: a tiny client for Open-Meteo, a free weather API that needs no key.

Two endpoints:
  geocoding  "Shanghai" -> latitude/longitude
  forecast   latitude/longitude -> current conditions + daily forecast

Docs: https://open-meteo.com/en/docs
"""
from dataclasses import dataclass

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Open-Meteo describes the sky with WMO weather codes (numbers). This maps the
# common ones to words. Anything missing shows as "code N".
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


def describe(code: int | None) -> str:
    return WEATHER_CODES.get(code, f"code {code}") if code is not None else "unknown"


@dataclass
class Place:
    name: str
    latitude: float
    longitude: float


def _get(url: str, params: dict) -> dict:
    """One HTTP GET returning parsed JSON. Kept separate so tests can replace it."""
    response = httpx.get(url, params=params, timeout=10)
    response.raise_for_status()  # turn 4xx/5xx into an exception
    return response.json()


def geocode(name: str) -> Place | None:
    """Find the best match for a place name, or None if nothing matches."""
    data = _get(GEOCODING_URL, {"name": name, "count": 1})
    results = data.get("results") or []
    if not results and "," in name:
        # The geocoder matches place names only, so "Berkeley, CA" finds
        # nothing. Retry with the part before the first comma.
        data = _get(GEOCODING_URL, {"name": name.split(",")[0].strip(), "count": 1})
        results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    label = ", ".join(p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p)
    return Place(name=label, latitude=r["latitude"], longitude=r["longitude"])


def forecast(latitude: float, longitude: float, days: int = 1, temperature_unit: str = "fahrenheit") -> dict:
    """Raw forecast JSON: `current` (right now) and `daily` (one entry per day)."""
    return _get(FORECAST_URL, {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",  # dates in the place's own time zone
        "forecast_days": days,
        "temperature_unit": temperature_unit,
        "wind_speed_unit": "mph" if temperature_unit == "fahrenheit" else "kmh",
    })
