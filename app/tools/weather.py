"""
The weather tool: a thin wrapper around integrations/openmeteo.py.

The integration returns Open-Meteo's raw JSON; this tool reshapes it into a
small, clearly labelled dict. Smaller tool results = fewer tokens and less
room for the model to misread a number.
"""
from typing import Annotated

from pydantic import Field

from app import config
from app.integrations import openmeteo
from app.tools.registry import Tier, tool


@tool(tier=Tier.READ)
def get_weather(
    place: Annotated[str | None, Field(description="City or place name, e.g. 'Shanghai'. Omit for Paul's home.")] = None,
    days: Annotated[int, Field(ge=1, le=7, description="Days of forecast, including today (1-7).")] = 1,
) -> dict:
    """Current weather and a daily forecast (high, low, chance of rain) for a place."""
    if place:
        found = openmeteo.geocode(place)
        if found is None:
            return {"error": f"No place found called {place!r}."}
    else:
        found = openmeteo.Place(config.HOME_NAME, config.HOME_LATITUDE, config.HOME_LONGITUDE)

    unit = config.TEMPERATURE_UNIT
    raw = openmeteo.forecast(found.latitude, found.longitude, days=days, temperature_unit=unit)
    symbol = "°F" if unit == "fahrenheit" else "°C"
    now, daily = raw["current"], raw["daily"]

    return {
        "place": found.name,
        "units": symbol,
        "now": {
            "conditions": openmeteo.describe(now["weather_code"]),
            "temperature": now["temperature_2m"],
            "feels_like": now["apparent_temperature"],
            "wind": f'{now["wind_speed_10m"]} {raw.get("current_units", {}).get("wind_speed_10m", "")}'.strip(),
        },
        # Open-Meteo returns parallel lists (all dates, all highs, ...);
        # zip() pairs them up into one dict per day.
        "daily": [
            {"date": d, "conditions": openmeteo.describe(code), "high": hi, "low": lo, "rain_chance_pct": rain}
            for d, code, hi, lo, rain in zip(
                daily["time"], daily["weather_code"], daily["temperature_2m_max"],
                daily["temperature_2m_min"], daily["precipitation_probability_max"],
            )
        ],
    }
