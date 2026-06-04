"""
Huertos Service — IA Endpoint: Recomendación de cultivos.

POST /api/huertos/recomendar

Flujo:
  1. Recibe coordenadas GPS del usuario (lat, lon) y municipio opcional.
  2. Consulta clima: OpenWeather → dataset CSV Veracruz → mock Fortín.
  3. Ejecuta el modelo Random Forest (.pkl) con features climáticas.
     ↳ Si no hay modelo: scoring térmico basado en la base de conocimiento.
  4. Retorna top-3 cultivos recomendados + justificación agroclimática.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os
import pickle
import numpy as np

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
    municipio: Optional[str] = Field(
        default=None,
        description="Nombre del municipio (opcional, ayuda al modelo de IA)",
    )
    huerto_id: Optional[str] = Field(
        default=None,
        description="ID del huerto (opcional, para guardar la recomendación)",
    )

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

# ---------------------------------------------------------------------------
# Base de conocimiento (para complementar al modelo real y para fallback mock)
# ---------------------------------------------------------------------------

_CULTIVOS_VERACRUZ = {
    "Platano": {
        "temporada_ideal": "Todo el año en clima cálido-húmedo",
        "rango_temperatura": "22–38°C",
        "tecnica_riego": "Goteo o aspersión, 2-3 veces por semana",
        "notas_veracruz": "Variedad Tabasco, dominante en la región de Fortín y Cosamaloapan.",
        "temp_min_ideal": 22.0, "temp_max_ideal": 38.0, "humedad_min": 70, "confianza_base": 0.91,
    },
    "Tomate": {
        "temporada_ideal": "Otoño-Invierno (Oct–Feb)",
        "rango_temperatura": "18–32°C",
        "tecnica_riego": "Goteo, cada 2 días",
        "notas_veracruz": "Alto rendimiento en Cotaxtla y Veracruz centro. Evitar calor extremo > 35°C.",
        "temp_min_ideal": 18.0, "temp_max_ideal": 32.0, "humedad_min": 50, "confianza_base": 0.87,
    },
    "Maiz": {
        "temporada_ideal": "Primavera-Verano (Mar–Ago)",
        "rango_temperatura": "20–35°C",
        "tecnica_riego": "Temporal o riego superficial, 1 vez por semana",
        "notas_veracruz": "Variedad nativa, resistente a sequía moderada.",
        "temp_min_ideal": 20.0, "temp_max_ideal": 35.0, "humedad_min": 60, "confianza_base": 0.85,
    },
    "Vainilla": {
        "temporada_ideal": "Todo el año (cosecha Nov–Feb)",
        "rango_temperatura": "20–30°C",
        "tecnica_riego": "Nebulización, alta humedad constante",
        "notas_veracruz": "Papantla, Veracruz — capital mundial de la vainilla. Requiere sombra y tutor.",
        "temp_min_ideal": 20.0, "temp_max_ideal": 30.0, "humedad_min": 80, "confianza_base": 0.83,
    },
    "Limon": {
        "temporada_ideal": "Todo el año",
        "rango_temperatura": "15–38°C",
        "tecnica_riego": "Goteo, cada 3-4 días en estiaje",
        "notas_veracruz": "Veracruz es el mayor productor nacional. Excelente para Martínez de la Torre.",
        "temp_min_ideal": 15.0, "temp_max_ideal": 38.0, "humedad_min": 50, "confianza_base": 0.88,
    },
    "Chile": {
        "temporada_ideal": "Primavera-Otoño (Mar–Nov)",
        "rango_temperatura": "18–32°C",
        "tecnica_riego": "Goteo, cada 2-3 días",
        "notas_veracruz": "Jalapa y región centro-norte de Veracruz. Alta demanda en agroindustria.",
        "temp_min_ideal": 18.0, "temp_max_ideal": 32.0, "humedad_min": 55, "confianza_base": 0.84,
    },
    "Cafe": {
        "temporada_ideal": "Cosecha Nov–Mar",
        "rango_temperatura": "16–24°C",
        "tecnica_riego": "Lluvia natural, alta humedad",
        "notas_veracruz": "Altitudes de 800–1400 msnm. Coatepec, Huatusco, Córdoba — café de exportación.",
        "temp_min_ideal": 16.0, "temp_max_ideal": 24.0, "humedad_min": 75, "confianza_base": 0.89,
    },
}

# Info por defecto si el RF predice algo que no tenemos detallado arriba
_DEFAULT_INFO = {
    "temporada_ideal": "Consultar calendario agrícola local",
    "rango_temperatura": "Adaptable a la zona",
    "tecnica_riego": "Riego regular según humedad del suelo",
    "notas_veracruz": "Cultivo con potencial productivo en el estado de Veracruz.",
    "temp_min_ideal": 15.0, "temp_max_ideal": 35.0, "humedad_min": 50, "confianza_base": 0.80,
}

def _recomendar_mock(temp_max: float, temp_min: float, humedad: int) -> list[dict]:
    recomendados = []
    for cultivo, c in _CULTIVOS_VERACRUZ.items():
        dentro_rango = (temp_min >= c["temp_min_ideal"] - 3 and temp_max <= c["temp_max_ideal"] + 3)
        humedad_ok = humedad >= c["humedad_min"] - 10
        if not dentro_rango:
            continue
        rango_centro = (c["temp_min_ideal"] + c["temp_max_ideal"]) / 2
        temp_centro = (temp_min + temp_max) / 2
        desviacion = abs(temp_centro - rango_centro) / (c["temp_max_ideal"] - c["temp_min_ideal"])
        confianza = round(c["confianza_base"] * (1 - desviacion * 0.3) * (1.05 if humedad_ok else 0.95), 2)
        confianza = max(0.50, min(0.99, confianza))

        recomendados.append({
            "cultivo": cultivo,
            "confianza": confianza,
            "justificacion": f"Temperatura máxima {temp_max}°C / mínima {temp_min}°C con {humedad}% humedad. Rango ideal: {c['rango_temperatura']}.",
            "temporada_ideal": c["temporada_ideal"],
            "rango_temperatura": c["rango_temperatura"],
            "tecnica_riego": c["tecnica_riego"],
            "notas_veracruz": c["notas_veracruz"],
        })
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
    clima_raw = await get_clima(lat=body.lat, lon=body.lon, municipio=body.municipio)

    # 2. Intentar cargar el modelo Random Forest real
    MODEL_PATH = os.path.join(
        os.path.dirname(__file__), "..", "models", "ml", "random_forest_huerto.pkl"
    )
    modo = "mock"
    modelo_version = "mock-v1.0"
    recomendaciones_raw = []

    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)

            modelo = bundle["modelo"]
            target_encoder = bundle["target_encoder"]
            label_encoders = bundle["label_encoders"]
            
            # Construir el vector de features exacto que el modelo espera
            feature_vector = []
            
            for feat in bundle["all_features"]:
                if feat == "temperatura":
                    feature_vector.append(clima_raw["temp_actual"])
                elif feat == "humedad_ambiental":
                    feature_vector.append(clima_raw["humedad"])
                elif feat == "probabilidad_lluvia":
                    feature_vector.append(clima_raw.get("probabilidad_lluvia", 30))
                elif feat == "lluvia_acumulada":
                    feature_vector.append(clima_raw.get("lluvia_acumulada", 50))
                elif feat == "velocidad_viento":
                    feature_vector.append(clima_raw.get("velocidad_viento", 15))
                elif feat == "radiacion_uv":
                    feature_vector.append(clima_raw.get("radiacion_uv", 6))
                elif feat == "humedad_suelo":
                    feature_vector.append(45.0)  # Default
                elif feat == "ultimo_riego":
                    feature_vector.append(2)  # Default
                elif feat == "dias_desde_siembra":
                    feature_vector.append(0)  # Recomendando para sembrar
                elif feat == "altitud_aproximada":
                    feature_vector.append(clima_raw.get("altitud", 100))
                elif feat in bundle["features_categoricas"]:
                    le = label_encoders[feat]
                    val = "desconocido"
                    if feat == "municipio":
                        val = clima_raw.get("ciudad", "Xalapa")
                    elif feat == "region":
                        val = clima_raw.get("region", "Capital")
                    elif feat == "temporada_ano":
                        val = clima_raw.get("temporada", "seca")
                    elif feat == "tipo_suelo":
                        val = "franco"
                    elif feat == "etapa_cultivo":
                        val = "siembra"
                    elif feat == "historial_plagas":
                        val = "alto"
                    
                    # Transformar (si el valor no existe en el encoder, usar la clase [0] por default)
                    try:
                        encoded = le.transform([val])[0]
                    except ValueError:
                        encoded = 0
                    feature_vector.append(encoded)

            X = np.array([feature_vector])
            probas = modelo.predict_proba(X)[0]
            
            # Obtener top 3 predicciones
            top3_indices = np.argsort(probas)[-3:][::-1]
            
            for idx in top3_indices:
                cultivo = target_encoder.inverse_transform([idx])[0]
                confianza = round(float(probas[idx]), 2)
                
                info = _CULTIVOS_VERACRUZ.get(cultivo, _DEFAULT_INFO)
                
                recomendaciones_raw.append({
                    "cultivo": cultivo,
                    "confianza": confianza,
                    "justificacion": f"Modelo predictivo basado en {clima_raw['ciudad']}, temp: {clima_raw['temp_actual']}°C, humedad: {clima_raw['humedad']}%",
                    "temporada_ideal": info["temporada_ideal"],
                    "rango_temperatura": info["rango_temperatura"],
                    "tecnica_riego": info["tecnica_riego"],
                    "notas_veracruz": info["notas_veracruz"],
                })

            modo = "modelo_real"
            modelo_version = bundle.get("version", "random_forest-v1.0")

        except Exception as e:
            # Fallback al mock si algo falla con el modelo
            print(f"Error cargando modelo RF: {e}")
            recomendaciones_raw = []

    if not recomendaciones_raw:
        recomendaciones_raw = _recomendar_mock(clima_raw["temp_max"], clima_raw["temp_min"], clima_raw["humedad"])

    if not recomendaciones_raw:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No se encontraron cultivos compatibles con temp_max={clima_raw['temp_max']}°C "
                f"y temp_min={clima_raw['temp_min']}°C. Verifica las coordenadas."
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
