"""The weather tool, with Open-Meteo replaced by canned responses (no network)."""
import json

import pytest

from app.integrations import openmeteo
from app.tools import registry

# Shaped like Open-Meteo's real responses (https://open-meteo.com/en/docs).
FORECAST = {
    "current_units": {"wind_speed_10m": "mp/h"},
    "current": {"time": "2026-10-05T09:00", "temperature_2m": 61.3, "apparent_temperature": 60.1,
                "weather_code": 2, "wind_speed_10m": 7.4},
    "daily": {"time": ["2026-10-05", "2026-10-06"], "weather_code": [2, 61],
              "temperature_2m_max": [68.0, 63.5], "temperature_2m_min": [54.1, 55.0],
              "precipitation_probability_max": [5, 70]},
}
SHANGHAI = {"results": [{"name": "Shanghai", "admin1": "Shanghai", "country": "China",
                         "latitude": 31.22, "longitude": 121.46}]}


@pytest.fixture
def fake_http(monkeypatch):
    requests = []

    def fake_get(url, params):
        requests.append((url, params))
        if url == openmeteo.GEOCODING_URL:
            return SHANGHAI if params["name"] in ("Shanghai", "Berkeley") else {}
        return FORECAST

    monkeypatch.setattr(openmeteo, "_get", fake_get)
    return requests


def test_home_weather_needs_no_geocoding(fake_http):
    result = registry.run("get_weather", "{}")
    data = json.loads(result.text)
    assert result.ok
    assert data["now"]["conditions"] == "partly cloudy"
    assert data["now"]["wind"] == "7.4 mp/h"
    assert data["daily"][1] == {"date": "2026-10-06", "conditions": "light rain",
                                "high": 63.5, "low": 55.0, "rain_chance_pct": 70}
    assert [url for url, _ in fake_http] == [openmeteo.FORECAST_URL]


def test_named_place_is_geocoded(fake_http):
    data = json.loads(registry.run("get_weather", '{"place": "Shanghai", "days": 2}').text)
    assert data["place"] == "Shanghai, Shanghai, China"
    url, params = fake_http[-1]
    assert params["latitude"] == 31.22 and params["forecast_days"] == 2


def test_place_with_state_retries_without_it(fake_http):
    registry.run("get_weather", '{"place": "Berkeley, CA"}')
    names = [p["name"] for url, p in fake_http if url == openmeteo.GEOCODING_URL]
    assert names == ["Berkeley, CA", "Berkeley"]


def test_unknown_place(fake_http):
    data = json.loads(registry.run("get_weather", '{"place": "Atlantis"}').text)
    assert "No place found" in data["error"]
