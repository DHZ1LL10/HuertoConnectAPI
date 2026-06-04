"""
Plagas Service — IA Endpoint: Detección de plagas.

POST /api/plagas/detectar

Flujo:
  1. Recibe imagen en base64 (o URL de imagen ya subida a Cloudinary).
  2. Ejecuta el modelo YOLOv8n / CNN (.pt) sobre la imagen.
     ↳ Mientras el modelo no esté disponible: devuelve mock con plaga
       detectada y tratamientos ecológicos reales de Veracruz.
  3. Cruza el resultado con la base de datos de tratamientos ecológicos.
  4. Retorna: plaga detectada, confianza, severidad, y métodos ecológicos de mitigación.

Para conectar el modelo real:
  - Coloca el archivo .pt en: plagas-service/app/models/ml/yolov8n_plagas.pt
  - Descomenta la sección "MODELO REAL" y comenta el bloque "MOCK".
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from shared.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/plagas", tags=["IA — Detección de Plagas"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class DetectarRequest(BaseModel):
    imagen_url: str = Field(
        description="URL de la imagen ya subida (usar POST /api/plagas/upload-imagen primero)",
    )
    huerto_id: Optional[str] = Field(default=None)
    cultivo_id: Optional[str] = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "example": {
                "imagen_url": "https://res.cloudinary.com/demo/image/upload/v1/plagas/muestra.jpg",
                "huerto_id": "6a20978432614f95d7d91e5b",
                "cultivo_id": None,
            }
        }
    }


class TratamientoEcologico(BaseModel):
    nombre: str
    tipo: str = Field(description="biologico | botanico | cultural | fisico")
    descripcion: str
    aplicacion: str
    frecuencia: str
    disponible_veracruz: bool


class DeteccionResult(BaseModel):
    plaga: str
    nombre_cientifico: str
    confianza: float = Field(description="Confianza del modelo (0.0 - 1.0)")
    severidad: str = Field(description="Baja | Media | Alta | Critica")
    descripcion_plaga: str
    cultivos_afectados: list[str]
    tratamientos_ecologicos: list[TratamientoEcologico]
    alerta_recomendada: bool


class DetectarResponse(BaseModel):
    deteccion: DeteccionResult
    imagen_analizada: str
    modelo_version: str
    modo: str = Field(description="'modelo_real' o 'mock'")
    mensaje: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "deteccion": {
                    "plaga": "Trips",
                    "nombre_cientifico": "Frankliniella occidentalis",
                    "confianza": 0.89,
                    "severidad": "Media",
                    "descripcion_plaga": "Insecto picador-chupador que daña flores y frutos.",
                    "cultivos_afectados": ["Chile", "Jitomate", "Aguacate"],
                    "tratamientos_ecologicos": [],
                    "alerta_recomendada": True,
                },
                "imagen_analizada": "https://res.cloudinary.com/...",
                "modelo_version": "mock-v1.0",
                "modo": "mock",
                "mensaje": "Detección completada. Modo mock activo hasta integración del modelo .pt.",
            }
        }
    }


# ---------------------------------------------------------------------------
# Base de conocimiento: Plagas + Tratamientos ecológicos de Veracruz
# ---------------------------------------------------------------------------

_TRATAMIENTOS_DB: dict[str, dict] = {
    "Trips": {
        "nombre_cientifico": "Frankliniella occidentalis",
        "descripcion_plaga": (
            "Insecto picador-chupador microscópico. Daña flores, frutos y hojas jóvenes "
            "causando deformaciones y transmite virus como el TSWV."
        ),
        "cultivos_afectados": ["Chile", "Jitomate", "Aguacate", "Cebolla", "Fresa"],
        "severidad_default": "Media",
        "tratamientos": [
            {
                "nombre": "Beauveria bassiana",
                "tipo": "biologico",
                "descripcion": "Hongo entomopatógeno que parasita trips adultos y ninfas.",
                "aplicacion": "Aspersión foliar en horas frescas (mañana o tarde)",
                "frecuencia": "Cada 7 días durante infestación activa",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Aceite de Neem (Azadiractina)",
                "tipo": "botanico",
                "descripcion": "Inhibe la muda y alimentación de trips. Efecto repelente.",
                "aplicacion": "Dilución 2–3 mL/L + jabón potásico. Aspersión foliar.",
                "frecuencia": "Cada 5–7 días, 3 aplicaciones consecutivas",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Trampas azules adhesivas",
                "tipo": "fisico",
                "descripcion": "Los trips son atraídos por el color azul. Monitoreo y captura masiva.",
                "aplicacion": "1 trampa cada 100 m², a nivel de dosel",
                "frecuencia": "Permanente, revisar y cambiar cada 2-3 semanas",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Rotación de cultivos",
                "tipo": "cultural",
                "descripcion": "Rompe el ciclo de vida. Alternar con cultivos no hospederos.",
                "aplicacion": "Planificación de siembra entre ciclos",
                "frecuencia": "Por ciclo agrícola",
                "disponible_veracruz": True,
            },
        ],
    },
    "Mosca Blanca": {
        "nombre_cientifico": "Bemisia tabaci / Trialeurodes vaporariorum",
        "descripcion_plaga": (
            "Plaga clave en cultivos de Veracruz. Succiona savia y excreta melaza que "
            "favorece la fumagina. Vectora de begomovirus graves."
        ),
        "cultivos_afectados": ["Jitomate", "Chile", "Pepino", "Melón", "Frijol"],
        "severidad_default": "Alta",
        "tratamientos": [
            {
                "nombre": "Encarsia formosa (parasitoide)",
                "tipo": "biologico",
                "descripcion": "Avispa parasitoide específica de mosca blanca. Control biológico clásico.",
                "aplicacion": "Liberación en invernadero o campo: 1 adulto/m²",
                "frecuencia": "Liberaciones semanales por 4–6 semanas",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Jabón potásico",
                "tipo": "botanico",
                "descripcion": "Destruye la cutícula de ninfas y adultos por contacto.",
                "aplicacion": "Solución 15 g/L, aspersión directa al envés de hojas",
                "frecuencia": "Cada 4–5 días durante 3 semanas",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Trampas amarillas adhesivas",
                "tipo": "fisico",
                "descripcion": "Captura masiva de adultos. Indispensable para monitoreo.",
                "aplicacion": "2–4 trampas por surco de 100 m",
                "frecuencia": "Permanente durante el ciclo",
                "disponible_veracruz": True,
            },
        ],
    },
    "Roya": {
        "nombre_cientifico": "Hemileia vastatrix (café) / Phakopsora pachyrhizi (soya)",
        "descripcion_plaga": (
            "Hongo foliar que produce pústulas de color naranja-café en el envés de hojas. "
            "En Veracruz afecta principalmente café (Coatepec, Huatusco, Córdoba)."
        ),
        "cultivos_afectados": ["Café", "Frijol", "Soya", "Trigo"],
        "severidad_default": "Alta",
        "tratamientos": [
            {
                "nombre": "Caldo Bordelés (Sulfato de Cobre + Cal)",
                "tipo": "botanico",
                "descripcion": "Fungicida de contacto con cobre. Protector y curativo en etapas tempranas.",
                "aplicacion": "Solución 1%: 10 g CuSO4 + 10 g cal / L agua. Aspersión foliar.",
                "frecuencia": "Preventiva cada 15 días en temporada de lluvia",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Trichoderma harzianum",
                "tipo": "biologico",
                "descripcion": "Hongo antagonista que inhibe el desarrollo de la roya.",
                "aplicacion": "Aspersión foliar con solución 10⁸ esporas/mL",
                "frecuencia": "Cada 15 días como preventivo",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Poda sanitaria",
                "tipo": "cultural",
                "descripcion": "Eliminar y quemar ramas y hojas infectadas para reducir inóculo.",
                "aplicacion": "Retirar material afectado en bolsas selladas",
                "frecuencia": "Al detectar los primeros síntomas y después de cada lluvia fuerte",
                "disponible_veracruz": True,
            },
        ],
    },
    "Áfidos": {
        "nombre_cientifico": "Myzus persicae / Aphis gossypii",
        "descripcion_plaga": (
            "Insectos pequeños que colonizan brotes y envés de hojas. "
            "Transmiten virus y producen melaza que atrae hormigas."
        ),
        "cultivos_afectados": ["Chile", "Jitomate", "Pepino", "Limón", "Maíz"],
        "severidad_default": "Baja",
        "tratamientos": [
            {
                "nombre": "Chrysoperla carnea (crisopa verde)",
                "tipo": "biologico",
                "descripcion": "Depredador voraz de áfidos. Las larvas consumen hasta 400 áfidos/día.",
                "aplicacion": "Liberación de huevos o larvas: 5,000 unidades/ha",
                "frecuencia": "Una liberación inicial, evaluar a las 2 semanas",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Extracto de ajo + chile",
                "tipo": "botanico",
                "descripcion": "Repelente natural. Capsaicina y alicina ahuyentan colonias de áfidos.",
                "aplicacion": "Macerado: 50 g ajo + 50 g chile / L agua. Filtrar y diluir 1:10.",
                "frecuencia": "Cada 5 días hasta eliminar colonias",
                "disponible_veracruz": True,
            },
            {
                "nombre": "Control de hormigas",
                "tipo": "cultural",
                "descripcion": "Las hormigas protegen a los áfidos. Eliminar hormigueros reduce infestación.",
                "aplicacion": "Bandas de pegamento en tallos + eliminación de nidos",
                "frecuencia": "Control permanente",
                "disponible_veracruz": True,
            },
        ],
    },
    "Sin Plaga": {
        "nombre_cientifico": "N/A",
        "descripcion_plaga": "No se detectó presencia de plaga en la imagen analizada.",
        "cultivos_afectados": [],
        "severidad_default": "Baja",
        "tratamientos": [
            {
                "nombre": "Monitoreo preventivo",
                "tipo": "cultural",
                "descripcion": "Continuar con revisiones periódicas cada 7 días.",
                "aplicacion": "Inspección visual de hojas, tallos y frutos",
                "frecuencia": "Semanal",
                "disponible_veracruz": True,
            }
        ],
    },
}

# Lista de plagas para el mock (se rota para simular detecciones variadas)
_PLAGAS_MOCK = ["Trips", "Mosca Blanca", "Roya", "Áfidos"]


def _detectar_mock(imagen_url: str) -> dict:
    """
    Simula la salida del modelo YOLOv8n / CNN.
    Selecciona una plaga basada en el hash de la URL para ser determinista.
    """
    # Determinista: misma URL → misma plaga (útil para demos)
    idx = hash(imagen_url) % len(_PLAGAS_MOCK)
    plaga_nombre = _PLAGAS_MOCK[idx]
    datos = _TRATAMIENTOS_DB[plaga_nombre]

    # Simular confianza y severidad
    confianza = round(0.72 + (hash(imagen_url + "conf") % 27) / 100, 2)
    severidades = ["Baja", "Media", "Alta"]
    severidad = severidades[hash(imagen_url + "sev") % 3]
    alerta = severidad in ("Alta", "Critica")

    return {
        "plaga": plaga_nombre,
        "nombre_cientifico": datos["nombre_cientifico"],
        "confianza": confianza,
        "severidad": severidad,
        "descripcion_plaga": datos["descripcion_plaga"],
        "cultivos_afectados": datos["cultivos_afectados"],
        "tratamientos_ecologicos": datos["tratamientos"],
        "alerta_recomendada": alerta,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/detectar",
    response_model=DetectarResponse,
    summary="IA — Detecta plaga en imagen y devuelve tratamientos ecológicos",
)
async def detectar_plaga(
    body: DetectarRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analiza una imagen de cultivo y detecta la plaga presente.

    - **imagen_url**: URL de imagen previamente subida con `POST /api/plagas/upload-imagen`.
    - Retorna la plaga detectada, nivel de confianza, severidad y **métodos ecológicos
      de mitigación** específicos para la región de Veracruz.
    - En modo mock: detección determinista basada en la URL de la imagen.
    - Cuando el modelo `.pt` esté disponible, se cargará automáticamente desde
      `plagas-service/app/models/ml/yolov8n_plagas.pt`.
    """
    if not body.imagen_url:
        raise HTTPException(status_code=400, detail="Se requiere imagen_url.")

    # === MODELO REAL (descomentar cuando tengas el .pt) ===
    # import os
    # MODEL_PATH = "app/models/ml/yolov8n_plagas.pt"
    # if os.path.exists(MODEL_PATH):
    #     from ultralytics import YOLO
    #     model = YOLO(MODEL_PATH)
    #     # Descargar imagen de la URL y procesarla
    #     import httpx, tempfile
    #     async with httpx.AsyncClient() as client:
    #         img_resp = await client.get(body.imagen_url)
    #     with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
    #         f.write(img_resp.content)
    #         tmp_path = f.name
    #     results = model(tmp_path)
    #     # Mapear resultados al diccionario de tratamientos
    #     # plaga_nombre = results[0].names[results[0].probs.top1]
    #     # confianza = float(results[0].probs.top1conf)
    #     # datos = _TRATAMIENTOS_DB.get(plaga_nombre, _TRATAMIENTOS_DB["Sin Plaga"])
    #     modo = "modelo_real"
    #     modelo_version = "yolov8n-plagas-v1.0"

    # === MOCK (activo hasta que llegue el .pt) ===
    modo = "mock"
    modelo_version = "mock-v1.0"
    deteccion_raw = _detectar_mock(body.imagen_url)

    # Construir respuesta
    tratamientos = [TratamientoEcologico(**t) for t in deteccion_raw["tratamientos_ecologicos"]]

    return DetectarResponse(
        deteccion=DeteccionResult(
            plaga=deteccion_raw["plaga"],
            nombre_cientifico=deteccion_raw["nombre_cientifico"],
            confianza=deteccion_raw["confianza"],
            severidad=deteccion_raw["severidad"],
            descripcion_plaga=deteccion_raw["descripcion_plaga"],
            cultivos_afectados=deteccion_raw["cultivos_afectados"],
            tratamientos_ecologicos=tratamientos,
            alerta_recomendada=deteccion_raw["alerta_recomendada"],
        ),
        imagen_analizada=body.imagen_url,
        modelo_version=modelo_version,
        modo=modo,
        mensaje=(
            "Detección completada en modo mock. "
            "Integra el modelo .pt en plagas-service/app/models/ml/ para activar la IA real."
            if modo == "mock"
            else "Detección completada con modelo real."
        ),
    )
