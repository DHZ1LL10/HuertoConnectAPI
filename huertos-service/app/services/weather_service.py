"""
Huertos Service — Servicio de clima enriquecido con datos de Veracruz.

Prioridad de fuentes:
  1. OpenWeatherMap (si hay API key activa y funciona) → datos en tiempo real
  2. Dataset clima_veracruz.csv (siempre disponible) → datos históricos reales por municipio/mes
  3. Mock de Fortín de las Flores → último recurso

Municipios disponibles en el dataset:
  Xalapa, Coatepec, Cordoba, Orizaba, Veracruz, Alvarado, Papantla,
  Martinez de la Torre, Tuxpan, Panuco, Cosamaloapan, San Andres Tuxtla,
  Minatitlan, Acayucan, Perote, Huatusco
"""

import os
import csv
from datetime import datetime, timezone
from typing import Optional
import httpx

from shared.config import settings

# ─── Rutas ────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CLIMA_CSV = os.path.join(_BASE_DIR, "..", "..", "..", "clima_veracruz.csv")

# ─── Caché en memoria del CSV (se carga una vez al primer uso) ────────────────
_CLIMA_CACHE: dict[tuple[str, int], dict] = {}
_CACHE_LOADED = False


def _normalize(s: str) -> str:
    """Normaliza texto para comparación: minúsculas, sin acentos."""
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
        "ñ": "n", "Ñ": "n",
    }
    s = s.lower().strip()
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s


def _load_clima_csv() -> None:
    """Carga el CSV de clima una sola vez y lo guarda en caché."""
    global _CACHE_LOADED

    paths_to_try = [
        _CLIMA_CSV,
        os.path.join(_BASE_DIR, "clima_veracruz.csv"),
        "/app/clima_veracruz.csv",
    ]

    for path in paths_to_try:
        if not os.path.exists(path):
            continue
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    municipio = _normalize(row.get("municipio", ""))
                    fecha = row.get("fecha", "")
                    if not municipio or not fecha:
                        continue
                    try:
                        mes = int(fecha.split("-")[1])
                    except (IndexError, ValueError):
                        continue
                    _CLIMA_CACHE[(municipio, mes)] = {
                        "temp_max": float(row.get("temperatura_maxima", 30)),
                        "temp_min": float(row.get("temperatura_minima", 18)),
                        "temp_actual": float(row.get("temperatura_promedio", 24)),
                        "humedad": int(float(row.get("humedad", 70))),
                        "descripcion": row.get("condicion_climatica", "despejado").capitalize(),
                        "temporada": row.get("temporada", "seca"),
                        "altitud": int(float(row.get("altitud", 100))),
                        "region": row.get("region", ""),
                        "probabilidad_lluvia": float(row.get("probabilidad_lluvia", 30)),
                        "lluvia_acumulada": float(row.get("lluvia_acumulada", 50)),
                        "velocidad_viento": float(row.get("velocidad_viento", 15)),
                        "radiacion_uv": float(row.get("radiacion_uv", 6)),
                        "ciudad": row.get("municipio", municipio),
                        "fuente": "dataset_veracruz",
                    }
            _CACHE_LOADED = True
            return
        except Exception:
            continue

    _CACHE_LOADED = True  # marcar como intentado aunque falle


def get_clima_por_municipio(municipio: str, mes: Optional[int] = None) -> Optional[dict]:
    """
    Devuelve los datos climáticos del municipio para el mes indicado
    usando el dataset clima_veracruz.csv.

    Args:
        municipio: Nombre del municipio (ej: "Fortín de las Flores", "Xalapa")
        mes: Número de mes 1–12. Por defecto: mes actual.

    Returns:
        Dict con clima o None si el municipio no está en el dataset.
    """
    global _CACHE_LOADED
    if not _CACHE_LOADED:
        _load_clima_csv()

    if mes is None:
        mes = datetime.now(timezone.utc).month

    key = (_normalize(municipio), mes)
    resultado = _CLIMA_CACHE.get(key)

    # Intento con municipio parcial si no hay match exacto
    if resultado is None:
        mun_norm = _normalize(municipio)
        for (m, mo), datos in _CLIMA_CACHE.items():
            if mun_norm in m or m in mun_norm:
                if mo == mes:
                    resultado = datos
                    break

    return resultado


def get_municipios_disponibles() -> list[str]:
    """Retorna la lista de municipios en el dataset."""
    global _CACHE_LOADED
    if not _CACHE_LOADED:
        _load_clima_csv()
    municipios = sorted(set(datos["ciudad"] for datos in _CLIMA_CACHE.values()))
    return municipios


# ─── Fallback mock: Fortín de las Flores ─────────────────────────────────────
_MOCK_FORTIN = {
    "temp_max": 34.5,
    "temp_min": 19.8,
    "temp_actual": 27.2,
    "humedad": 78,
    "descripcion": "Parcialmente nublado",
    "temporada": "lluvias",
    "altitud": 920,
    "region": "Montanas",
    "probabilidad_lluvia": 65.0,
    "lluvia_acumulada": 180.0,
    "velocidad_viento": 12.0,
    "radiacion_uv": 7.5,
    "ciudad": "Fortín de las Flores",
    "fuente": "mock",
}


async def get_clima(
    lat: float = 18.9994,
    lon: float = -96.9389,
    municipio: Optional[str] = None,
) -> dict:
    """
    Obtiene el clima con la siguiente prioridad:
      1. OpenWeatherMap (si hay API key válida)
      2. Dataset clima_veracruz.csv (si municipio está en el dataset)
      3. Mock de Fortín de las Flores

    Args:
        lat: Latitud (para OpenWeather)
        lon: Longitud (para OpenWeather)
        municipio: Si se especifica, busca primero en el dataset local.

    Returns:
        Dict con temp_max, temp_min, temp_actual, humedad, temporada, fuente, etc.
    """
    # ── 1. Intentar OpenWeather ───────────────────────────────────────────────
    api_key: str = getattr(settings, "OPENWEATHER_API_KEY", "")
    if api_key and api_key not in ("", "your-openweather-api-key", "TU_API_KEY"):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric", "lang": "es"},
                )
                resp.raise_for_status()
                data = resp.json()

            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            mes_actual = datetime.now(timezone.utc).month
            ciudad = data.get("name", municipio or "Veracruz")

            # Complementar con datos del dataset si el municipio coincide
            dataset_datos = get_clima_por_municipio(ciudad, mes_actual) or {}

            return {
                "temp_max": round(main.get("temp_max", main.get("temp", 30)), 1),
                "temp_min": round(main.get("temp_min", main.get("temp", 18)), 1),
                "temp_actual": round(main.get("temp", 25), 1),
                "humedad": main.get("humidity", 70),
                "descripcion": weather.get("description", "despejado").capitalize(),
                "temporada": dataset_datos.get("temporada", "seca" if mes_actual in [11, 12, 1, 2, 3, 4] else "lluvias"),
                "altitud": dataset_datos.get("altitud", 100),
                "region": dataset_datos.get("region", ""),
                "probabilidad_lluvia": dataset_datos.get("probabilidad_lluvia", 30.0),
                "lluvia_acumulada": dataset_datos.get("lluvia_acumulada", 50.0),
                "velocidad_viento": round(data.get("wind", {}).get("speed", 10) * 3.6, 1),
                "radiacion_uv": dataset_datos.get("radiacion_uv", 6.0),
                "ciudad": ciudad,
                "fuente": "openweathermap",
            }
        except Exception:
            pass  # fallback al dataset

    # ── 2. Intentar dataset local ─────────────────────────────────────────────
    mun = municipio or "Fortin de las Flores"
    mes_actual = datetime.now(timezone.utc).month
    datos = get_clima_por_municipio(mun, mes_actual)
    if datos:
        return datos

    # ── 3. Mock Fortín ────────────────────────────────────────────────────────
    return _MOCK_FORTIN.copy()
