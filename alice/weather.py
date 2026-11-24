"""Keyless current-weather lookup using Open-Meteo's public APIs."""
from __future__ import annotations

import math


_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Light freezing rain",
    67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
    77: "Snow grains", 80: "Light rain showers", 81: "Rain showers",
    82: "Heavy rain showers", 85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}


class OpenMeteoWeather:
    """Resolve a place and return current conditions, with no account key."""

    def __init__(self, get=None, timeout=8):
        self._get = get
        self.timeout = max(1, min(int(timeout), 10))

    def _request(self, url, params):
        get = self._get
        if get is None:
            import requests
            get = requests.get
        response = get(url, params=params, timeout=self.timeout, allow_redirects=False)
        if int(getattr(response, "status_code", 0)) != 200:
            raise RuntimeError(f"Weather service returned HTTP {getattr(response, 'status_code', 'unknown')}.")
        return response.json()

    def lookup(self, location):
        place = str(location or "").strip()
        if not place or len(place) > 120 or any(ord(char) < 32 for char in place):
            raise ValueError("Provide a location between 1 and 120 printable characters.")
        try:
            geocode = self._request(_GEOCODING_URL, {
                "name": place, "count": 3, "language": "en", "format": "json",
            })
            matches = geocode.get("results") if isinstance(geocode, dict) else None
            if not isinstance(matches, list) or not matches:
                return {"ok": False, "error": "No matching location was found.", "source": "open-meteo"}
            selected = matches[0]
            latitude = float(selected["latitude"])
            longitude = float(selected["longitude"])
            if not (math.isfinite(latitude) and -90 <= latitude <= 90
                    and math.isfinite(longitude) and -180 <= longitude <= 180):
                raise ValueError("Geocoding returned invalid coordinates.")
            forecast = self._request(_FORECAST_URL, {
                "latitude": latitude, "longitude": longitude, "timezone": "auto",
                "current": "temperature_2m,relative_humidity_2m,is_day,precipitation,weather_code,wind_speed_10m",
            })
            current = forecast.get("current") if isinstance(forecast, dict) else None
            if not isinstance(current, dict):
                raise RuntimeError("Weather service returned no current conditions.")
            code = int(current["weather_code"])
            country = str(selected.get("country") or "").strip()
            return {
                "ok": True,
                "location": ", ".join(part for part in (str(selected.get("name") or place).strip(), country) if part),
                "latitude": latitude,
                "longitude": longitude,
                "timezone": str(selected.get("timezone") or forecast.get("timezone") or ""),
                "observed_at": str(current.get("time") or ""),
                "temperature_c": float(current["temperature_2m"]),
                "relative_humidity_percent": int(current["relative_humidity_2m"]),
                "conditions": _WEATHER_CODES.get(code, f"Weather code {code}"),
                "wind_speed_kmh": float(current["wind_speed_10m"]),
                "precipitation_mm": float(current["precipitation"]),
                "is_day": bool(current["is_day"]),
                "source": "open-meteo",
                "attribution": "Weather data from Open-Meteo",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240], "source": "open-meteo"}


def verify_weather_lookup_postcondition(_args, result):
    from .execution.postconditions import PostconditionResult
    valid = (isinstance(result, dict) and result.get("ok") is True
             and result.get("source") == "open-meteo"
             and bool(result.get("location")) and bool(result.get("observed_at"))
             and isinstance(result.get("temperature_c"), (float, int)))
    return PostconditionResult(valid, {"observed": valid, "source": result.get("source") if isinstance(result, dict) else None},
                               "current weather fields read back" if valid else "weather_result_not_verified")
