"""
Huertos Service — Weather Service.

Consulta temperatura máxima/mínima del día actual en OpenWeatherMap
usando la API One Call 3.0 (o Current Weather como fallback).

Uso:
    from app.services.weather_service import get_clima

    clima = await get_clima(lat=18.9994, lon=-96.9389)
    # → {"temp_max": 34.2, "temp_min": 20.1, "descripcion": "nublado", "ciudad": "Fortín de las Flores"}
"""

import httpx
from typing import Optional

from shared.config import settings


# Coordenadas de Fortín de las Flores, Veracruz (usadas como fallback en demo)
FORTIN_LAT = 18.9994
FORTIN_LON = -96.9389

# Mock data para cuando no hay API key (demo / expociencia)
_MOCK_CLIMA_FORTIN = {
    "temp_max": 34.5,
    "temp_min": 19.8,
    "temp_actual": 27.2,
    "humedad": 78,
    "descripcion": "Parcialmente nublado",
    "ciudad": "Fortín de las Flores",
    "pais": "MX",
    "lat": FORTIN_LAT,
    "lon": FORTIN_LON,
    "fuente": "mock",
}


async def get_clima(
    lat: float = FORTIN_LAT,
    lon: float = FORTIN_LON,
) -> dict:
    """
    Obtiene el clima actual para las coordenadas dadas.

    Si OPENWEATHER_API_KEY no está configurada, devuelve mock data
    representativa de Fortín de las Flores, Veracruz.

    Args:
        lat: Latitud (default: Fortín de las Flores).
        lon: Longitud (default: Fortín de las Flores).

    Returns:
        Dict con temp_max, temp_min, temp_actual, humedad, descripcion, ciudad, fuente.
    """
    api_key: Optional[str] = getattr(settings, "OPENWEATHER_API_KEY", None)

    if not api_key or api_key in ("", "your-openweather-api-key", "TU_API_KEY"):
        # Sin key: devolver mock de Fortín de las Flores para la demo
        mock = _MOCK_CLIMA_FORTIN.copy()
        mock["lat"] = lat
        mock["lon"] = lon
        return mock

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
        "lang": "es",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]

        return {
            "temp_max": round(main.get("temp_max", main.get("temp", 25.0)), 1),
            "temp_min": round(main.get("temp_min", main.get("temp", 18.0)), 1),
            "temp_actual": round(main.get("temp", 25.0), 1),
            "humedad": main.get("humidity", 70),
            "descripcion": weather.get("description", "despejado").capitalize(),
            "ciudad": data.get("name", "Desconocida"),
            "pais": data.get("sys", {}).get("country", "MX"),
            "lat": lat,
            "lon": lon,
            "fuente": "openweathermap",
        }

    except httpx.HTTPStatusError as exc:
        # Key inválida o error de la API → fallback a mock
        mock = _MOCK_CLIMA_FORTIN.copy()
        mock["lat"] = lat
        mock["lon"] = lon
        mock["fuente"] = f"mock (error HTTP {exc.response.status_code})"
        return mock

    except Exception:
        # Timeout, red caída, etc. → fallback a mock
        mock = _MOCK_CLIMA_FORTIN.copy()
        mock["lat"] = lat
        mock["lon"] = lon
        mock["fuente"] = "mock (sin conexión)"
        return mock
