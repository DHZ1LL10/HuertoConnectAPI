"""
Huertos Service — IA Endpoint: Recomendación de cultivos.

POST /api/huertos/recomendar

Flujo:
  1. Recibe coordenadas GPS del usuario (lat, lon).
  2. Consulta OpenWeatherMap para obtener temp_max y temp_min del día.
  3. Ejecuta el modelo Random Forest (.pkl) con esos datos.
     ↳ Mientras el modelo no esté disponible: devuelve mock con cultivos
       recomendados para Veracruz según las temperaturas reales.
  4. Retorna el cultivo recomendado + justificación agroclimática.

Para conectar el modelo real:
  - Coloca el archivo .pkl en: huertos-service/app/models/ml/random_forest_cultivos.pkl
  - Descomenta la sección "MODELO REAL" y comenta el bloque "MOCK".
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os

from app.services.weather_service import get_clima
from shared.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/huertos", tags=["IA — Recomendación de Cultivos"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RecomendarRequest(BaseModel):
    lat: float = Field(
        default=18.9994,
        ge=-90, le=90,
        description="Latitud de la ubicación del huerto",
    )
    lon: float = Field(
        default=-96.9389,
        ge=-180, le=180,
        description="Longitud de la ubicación del huerto",
    )
    huerto_id: Optional[str] = Field(
        default=None,
        description="ID del huerto (opcional, para guardar la recomendación)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "lat": 18.9994,
                "lon": -96.9389,
                "huerto_id": None,
            }
        }
    }


class ClimaData(BaseModel):
    temp_max: float
    temp_min: float
    temp_actual: float
    humedad: int
    descripcion: str
    ciudad: str
    fuente: str


class RecomendacionItem(BaseModel):
    cultivo: str
    confianza: float = Field(description="Confianza del modelo (0.0 - 1.0)")
    justificacion: str
    temporada_ideal: str
    rango_temperatura: str
    tecnica_riego: str
    notas_veracruz: str


class RecomendarResponse(BaseModel):
    clima: ClimaData
    recomendaciones: list[RecomendacionItem]
    modelo_version: str
    modo: str = Field(description="'modelo_real' o 'mock' según si el .pkl está disponible")

    model_config = {
        "json_schema_extra": {
            "example": {
                "clima": {
                    "temp_max": 34.5,
                    "temp_min": 19.8,
                    "temp_actual": 27.2,
                    "humedad": 78,
                    "descripcion": "Parcialmente nublado",
                    "ciudad": "Fortín de las Flores",
                    "fuente": "openweathermap",
                },
                "recomendaciones": [
                    {
                        "cultivo": "Plátano Tabasco",
                        "confianza": 0.91,
                        "justificacion": "Temperatura óptima 25-35°C. Tu zona alcanzó 34.5°C máx con 78% de humedad.",
                        "temporada_ideal": "Todo el año en clima cálido-húmedo",
                        "rango_temperatura": "22–38°C",
                        "tecnica_riego": "Goteo o aspersión, 2-3 riegos por semana",
                        "notas_veracruz": "Variedad Tabasco ideal para municipios de la zona de Veracruz.",
                    }
                ],
                "modelo_version": "mock-v1.0",
                "modo": "mock",
            }
        }
    }


# ---------------------------------------------------------------------------
# Base de conocimiento agroclimática para Veracruz (mock del Random Forest)
# ---------------------------------------------------------------------------

# Catálogo de cultivos con rangos de temperatura para la región de Veracruz
_CULTIVOS_VERACRUZ = [
    {
        "cultivo": "Plátano Tabasco",
        "temp_min_ideal": 22.0,
        "temp_max_ideal": 38.0,
        "humedad_min": 70,
        "confianza_base": 0.91,
        "temporada_ideal": "Todo el año en clima cálido-húmedo",
        "rango_temperatura": "22–38°C",
        "tecnica_riego": "Goteo o aspersión, 2-3 veces por semana",
        "notas_veracruz": "Variedad Tabasco, dominante en la región de Fortín y Cosamaloapan.",
    },
    {
        "cultivo": "Jitomate Saladette",
        "temp_min_ideal": 18.0,
        "temp_max_ideal": 32.0,
        "humedad_min": 50,
        "confianza_base": 0.87,
        "temporada_ideal": "Otoño-Invierno (Oct–Feb)",
        "rango_temperatura": "18–32°C",
        "tecnica_riego": "Goteo, cada 2 días",
        "notas_veracruz": "Alto rendimiento en Cotaxtla y Veracruz centro. Evitar calor extremo > 35°C.",
    },
    {
        "cultivo": "Maíz Olotillo",
        "temp_min_ideal": 20.0,
        "temp_max_ideal": 35.0,
        "humedad_min": 60,
        "confianza_base": 0.85,
        "temporada_ideal": "Primavera-Verano (Mar–Ago)",
        "rango_temperatura": "20–35°C",
        "tecnica_riego": "Temporal o riego superficial, 1 vez por semana",
        "notas_veracruz": "Variedad nativa de la Sierra de Veracruz, resistente a sequía moderada.",
    },
    {
        "cultivo": "Vainilla Planifolia",
        "temp_min_ideal": 20.0,
        "temp_max_ideal": 30.0,
        "humedad_min": 80,
        "confianza_base": 0.83,
        "temporada_ideal": "Todo el año (cosecha Nov–Feb)",
        "rango_temperatura": "20–30°C",
        "tecnica_riego": "Nebulización, alta humedad constante",
        "notas_veracruz": "Papantla, Veracruz — capital mundial de la vainilla. Requiere sombra y tutor.",
    },
    {
        "cultivo": "Pimienta Gorda",
        "temp_min_ideal": 20.0,
        "temp_max_ideal": 36.0,
        "humedad_min": 70,
        "confianza_base": 0.80,
        "temporada_ideal": "Lluvia intensa (Jun–Sep)",
        "rango_temperatura": "20–36°C",
        "tecnica_riego": "Lluvia natural, complementar en secas",
        "notas_veracruz": "Zona huasteca y selva alta. Árbol perenne de alta rentabilidad.",
    },
    {
        "cultivo": "Limón Persa",
        "temp_min_ideal": 15.0,
        "temp_max_ideal": 38.0,
        "humedad_min": 50,
        "confianza_base": 0.88,
        "temporada_ideal": "Todo el año",
        "rango_temperatura": "15–38°C",
        "tecnica_riego": "Goteo, cada 3-4 días en estiaje",
        "notas_veracruz": "Veracruz es el mayor productor nacional. Excelente para Martínez de la Torre.",
    },
    {
        "cultivo": "Chile Jalapeño",
        "temp_min_ideal": 18.0,
        "temp_max_ideal": 32.0,
        "humedad_min": 55,
        "confianza_base": 0.84,
        "temporada_ideal": "Primavera-Otoño (Mar–Nov)",
        "rango_temperatura": "18–32°C",
        "tecnica_riego": "Goteo, cada 2-3 días",
        "notas_veracruz": "Jalapa y región centro-norte de Veracruz. Alta demanda en agroindustria.",
    },
    {
        "cultivo": "Café Arábica",
        "temp_min_ideal": 16.0,
        "temp_max_ideal": 24.0,
        "humedad_min": 75,
        "confianza_base": 0.89,
        "temporada_ideal": "Cosecha Nov–Mar",
        "rango_temperatura": "16–24°C",
        "tecnica_riego": "Lluvia natural, alta humedad",
        "notas_veracruz": "Altitudes de 800–1400 msnm. Coatepec, Huatusco, Córdoba — café de exportación.",
    },
]


def _recomendar_mock(temp_max: float, temp_min: float, humedad: int) -> list[dict]:
    """
    Lógica mock que simula la salida del Random Forest.
    Filtra y ordena cultivos según compatibilidad térmica con el clima actual.
    """
    recomendados = []

    for c in _CULTIVOS_VERACRUZ:
        # Score de compatibilidad térmica
        dentro_rango = (
            temp_min >= c["temp_min_ideal"] - 3
            and temp_max <= c["temp_max_ideal"] + 3
        )
        humedad_ok = humedad >= c["humedad_min"] - 10

        if not dentro_rango:
            continue

        # Ajustar confianza según qué tan centrado está en el rango ideal
        rango_centro = (c["temp_min_ideal"] + c["temp_max_ideal"]) / 2
        temp_centro = (temp_min + temp_max) / 2
        desviacion = abs(temp_centro - rango_centro) / (c["temp_max_ideal"] - c["temp_min_ideal"])
        confianza = round(c["confianza_base"] * (1 - desviacion * 0.3) * (1.05 if humedad_ok else 0.95), 2)
        confianza = max(0.50, min(0.99, confianza))

        recomendados.append({
            "cultivo": c["cultivo"],
            "confianza": confianza,
            "justificacion": (
                f"Temperatura máxima {temp_max}°C / mínima {temp_min}°C con {humedad}% humedad. "
                f"Rango ideal del cultivo: {c['rango_temperatura']}."
            ),
            "temporada_ideal": c["temporada_ideal"],
            "rango_temperatura": c["rango_temperatura"],
            "tecnica_riego": c["tecnica_riego"],
            "notas_veracruz": c["notas_veracruz"],
        })

    # Ordenar por confianza descendente, máximo 3 recomendaciones
    recomendados.sort(key=lambda x: x["confianza"], reverse=True)
    return recomendados[:3]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/recomendar",
    response_model=RecomendarResponse,
    summary="IA — Recomienda cultivos según clima real de la ubicación",
)
async def recomendar_cultivo(
    body: RecomendarRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Recibe coordenadas GPS, consulta el clima en tiempo real y devuelve
    los cultivos más recomendados para esa ubicación según el modelo de ML.

    - **lat / lon**: coordenadas del huerto del usuario.
    - Usa OpenWeatherMap para temperatura máx/mín del día.
    - El modelo Random Forest (.pkl) se carga automáticamente si existe en
      `huertos-service/app/models/ml/random_forest_cultivos.pkl`.
    - Si el modelo no está disponible, responde con mock data agroclimática
      real para Veracruz.
    """
    # 1. Obtener clima real (o mock si no hay API key)
    clima_raw = await get_clima(lat=body.lat, lon=body.lon)

    temp_max = clima_raw["temp_max"]
    temp_min = clima_raw["temp_min"]
    humedad = clima_raw["humedad"]

    # 2. Intentar cargar el modelo Random Forest real
    MODEL_PATH = os.path.join(
        os.path.dirname(__file__), "..", "models", "ml", "random_forest_cultivos.pkl"
    )
    modo = "mock"
    modelo_version = "mock-v1.0"

    # === MODELO REAL (descomentar cuando tengas el .pkl) ===
    # if os.path.exists(MODEL_PATH):
    #     import pickle
    #     import numpy as np
    #     with open(MODEL_PATH, "rb") as f:
    #         modelo = pickle.load(f)
    #     features = np.array([[temp_max, temp_min, humedad]])
    #     prediccion = modelo.predict(features)
    #     proba = modelo.predict_proba(features)
    #     # Mapear la predicción al cultivo y construir RecomendacionItem
    #     # ... (ajustar según las clases del modelo)
    #     modo = "modelo_real"
    #     modelo_version = "random_forest-v1.0"

    # === MOCK (activo hasta que llegue el .pkl) ===
    recomendaciones_raw = _recomendar_mock(temp_max, temp_min, humedad)

    if not recomendaciones_raw:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No se encontraron cultivos compatibles con temp_max={temp_max}°C "
                f"y temp_min={temp_min}°C. Verifica las coordenadas."
            ),
        )

    return RecomendarResponse(
        clima=ClimaData(
            temp_max=clima_raw["temp_max"],
            temp_min=clima_raw["temp_min"],
            temp_actual=clima_raw["temp_actual"],
            humedad=clima_raw["humedad"],
            descripcion=clima_raw["descripcion"],
            ciudad=clima_raw["ciudad"],
            fuente=clima_raw["fuente"],
        ),
        recomendaciones=[RecomendacionItem(**r) for r in recomendaciones_raw],
        modelo_version=modelo_version,
        modo=modo,
    )
