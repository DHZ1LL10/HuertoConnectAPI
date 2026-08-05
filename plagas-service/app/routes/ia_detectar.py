"""
Plagas Service — IA Endpoint: Detección de plagas con YOLOv8n.

POST /api/plagas/detectar

Flujo:
  1. Recibe la imagen directamente como archivo de imagen (multipart/form-data).
  2. Ejecuta el modelo YOLOv8n entrenado (best.pt) directamente sobre la imagen subida.
     ↳ Modelo entrenado con dataset veracruz_real — 10 clases:
       mosca_blanca, pulgon_verde, arana_roja, trips, minador,
       gusano_cogollero, cochinilla, roya, mildiu, mancha_foliar
  3. Cruza el resultado con la base de conocimiento de tratamientos ecológicos.
  4. Retorna: plaga detectada, confianza, severidad y métodos de mitigación.

Para activar el modelo real:
  - Coloca best.pt en: plagas-service/app/models/ml/best.pt
  - El endpoint lo detecta automáticamente y cambia de mock a modelo real.
"""

import hashlib
import os
import tempfile
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from typing import Optional

from shared.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/plagas", tags=["IA — Detección de Plagas"])


# ---------------------------------------------------------------------------
# Clases del modelo — data.yaml del entrenamiento de Gael
# ---------------------------------------------------------------------------

YOLO_CLASSES = {
    0: "mosca_blanca",
    1: "pulgon_verde",
    2: "arana_roja",
    3: "trips",
    4: "minador",
    5: "gusano_cogollero",
    6: "cochinilla",
    7: "roya",
    8: "mildiu",
    9: "mancha_foliar",
}

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "ml", "best.pt")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

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
    confianza: float
    severidad: str = Field(description="Baja | Media | Alta | Critica")
    descripcion_plaga: str
    cultivos_afectados: list[str]
    tratamientos_ecologicos: list[TratamientoEcologico]
    alerta_recomendada: bool
    mitigacion_viable: bool
    nota_mitigacion: Optional[str] = None


class DetectarResponse(BaseModel):
    deteccion: DeteccionResult
    imagen_analizada: str
    modelo_version: str
    modo: str
    mensaje: str


# ---------------------------------------------------------------------------
# Base de conocimiento — 10 plagas de Veracruz con tratamientos ecológicos
# ---------------------------------------------------------------------------

_TRATAMIENTOS_DB: dict[str, dict] = {
    "mosca_blanca": {
        "nombre_cientifico": "Bemisia tabaci / Trialeurodes vaporariorum",
        "descripcion_plaga": "Insecto chupador que coloniza el envés de las hojas. Excreta melaza que favorece la fumagina y transmite begomovirus.",
        "cultivos_afectados": ["Jitomate", "Chile", "Pepino", "Melón", "Frijol"],
        "severidad_default": "Alta",
        "mitigacion_viable": True,
        "nota_mitigacion": None,
        "tratamientos": [
            {"nombre": "Encarsia formosa", "tipo": "biologico", "descripcion": "Avispa parasitoide específica de mosca blanca.", "aplicacion": "Liberación 1 adulto/m² en campo o invernadero", "frecuencia": "Semanal por 4–6 semanas", "disponible_veracruz": True},
            {"nombre": "Jabón potásico", "tipo": "botanico", "descripcion": "Destruye la cutícula de ninfas y adultos por contacto directo.", "aplicacion": "15 g/L, aspersión directa al envés de hojas", "frecuencia": "Cada 4–5 días, 3 semanas", "disponible_veracruz": True},
            {"nombre": "Trampas amarillas adhesivas", "tipo": "fisico", "descripcion": "Captura masiva de adultos. Herramienta clave de monitoreo.", "aplicacion": "2–4 trampas por cada 100 m²", "frecuencia": "Permanente, cambiar cada 2–3 semanas", "disponible_veracruz": True},
            {"nombre": "Aceite de Neem (Azadiractina)", "tipo": "botanico", "descripcion": "Inhibe la muda y reproducción. Efecto repelente y ovicida.", "aplicacion": "2–3 mL/L + jabón potásico. Aspersión foliar.", "frecuencia": "Cada 7 días, 3 aplicaciones", "disponible_veracruz": True},
        ],
    },
    "pulgon_verde": {
        "nombre_cientifico": "Myzus persicae / Aphis gossypii",
        "descripcion_plaga": "Áfido verde que coloniza brotes y envés de hojas. Transmite virosis y produce melaza que atrae hormigas que los protegen.",
        "cultivos_afectados": ["Chile", "Jitomate", "Pepino", "Maíz", "Limón"],
        "severidad_default": "Media",
        "mitigacion_viable": True,
        "nota_mitigacion": None,
        "tratamientos": [
            {"nombre": "Chrysoperla carnea (crisopa)", "tipo": "biologico", "descripcion": "Larvas depredadoras vorazes. Consumen hasta 400 áfidos/día.", "aplicacion": "5,000 huevos o larvas/ha en liberación", "frecuencia": "Una liberación, evaluar a las 2 semanas", "disponible_veracruz": True},
            {"nombre": "Extracto de ajo y chile", "tipo": "botanico", "descripcion": "Alicina y capsaicina repelen y dañan colonias de pulgón.", "aplicacion": "50 g ajo + 50 g chile / L agua. Macerar, filtrar, diluir 1:10.", "frecuencia": "Cada 5 días hasta eliminar colonias", "disponible_veracruz": True},
            {"nombre": "Control de hormigas", "tipo": "cultural", "descripcion": "Las hormigas transportan y protegen a los pulgones. Eliminar nidos reduce la infestación.", "aplicacion": "Bandas de pegamento en tallos + eliminación de hormigueros", "frecuencia": "Control permanente durante el ciclo", "disponible_veracruz": True},
            {"nombre": "Jabón potásico", "tipo": "botanico", "descripcion": "Contacto directo rompe la cutícula del áfido.", "aplicacion": "15 g/L. Aspersión directa sobre colonias.", "frecuencia": "Cada 3–4 días hasta desaparecer", "disponible_veracruz": True},
        ],
    },
    "arana_roja": {
        "nombre_cientifico": "Tetranychus urticae",
        "descripcion_plaga": "Ácaro fitófago que succiona el contenido celular de las hojas. Produce un punteado amarillo fino. En infestaciones severas genera telarañas y defoliación. Se confunde visualmente con mancha foliar en etapas tempranas.",
        "cultivos_afectados": ["Fresa", "Pepino", "Chile", "Jitomate", "Maíz", "Frijol"],
        "severidad_default": "Alta",
        "mitigacion_viable": True,
        "nota_mitigacion": "Controlar en etapas tempranas. Alta resistencia a productos convencionales — rotar métodos.",
        "tratamientos": [
            {"nombre": "Phytoseiulus persimilis (ácaro depredador)", "tipo": "biologico", "descripcion": "Ácaro depredador específico de Tetranychus. Muy eficaz en invernadero.", "aplicacion": "50–100 adultos/m² sobre plantas infestadas", "frecuencia": "Liberación inicial, evaluar a los 10 días", "disponible_veracruz": True},
            {"nombre": "Aceite de Neem", "tipo": "botanico", "descripcion": "Inhibe la reproducción y muda. Eficaz contra huevos y ninfas.", "aplicacion": "3–5 mL/L + jabón potásico. Aspersión foliar envés.", "frecuencia": "Cada 5–7 días, 4 aplicaciones mínimo", "disponible_veracruz": True},
            {"nombre": "Azufre mojable", "tipo": "botanico", "descripcion": "Acaricida de contacto natural. Muy eficaz a temperaturas 20–32°C.", "aplicacion": "3 g/L. Aspersión foliar en horas frescas.", "frecuencia": "Cada 7–10 días. No aplicar con calor extremo.", "disponible_veracruz": True},
            {"nombre": "Aumento de humedad", "tipo": "cultural", "descripcion": "La araña roja prolifera en ambiente seco. Humedad > 70% reduce su reproducción.", "aplicacion": "Riego por aspersión o nebulización sobre el dosel", "frecuencia": "Diario en época seca", "disponible_veracruz": True},
        ],
    },
    "trips": {
        "nombre_cientifico": "Frankliniella occidentalis / Thrips tabaci",
        "descripcion_plaga": "Insecto picador-chupador microscópico. Daña flores, frutos y hojas jóvenes causando deformaciones plateadas. Transmite el virus TSWV.",
        "cultivos_afectados": ["Chile", "Jitomate", "Aguacate", "Cebolla", "Fresa"],
        "severidad_default": "Media",
        "mitigacion_viable": True,
        "nota_mitigacion": None,
        "tratamientos": [
            {"nombre": "Beauveria bassiana", "tipo": "biologico", "descripcion": "Hongo entomopatógeno que parasita trips adultos y ninfas.", "aplicacion": "Aspersión foliar en horas frescas (mañana o tarde)", "frecuencia": "Cada 7 días durante infestación activa", "disponible_veracruz": True},
            {"nombre": "Aceite de Neem (Azadiractina)", "tipo": "botanico", "descripcion": "Inhibe la muda y alimentación. Efecto repelente.", "aplicacion": "2–3 mL/L + jabón potásico. Aspersión foliar.", "frecuencia": "Cada 5–7 días, 3 aplicaciones", "disponible_veracruz": True},
            {"nombre": "Trampas azules adhesivas", "tipo": "fisico", "descripcion": "Los trips son fuertemente atraídos por el azul. Captura masiva y monitoreo.", "aplicacion": "1 trampa cada 100 m², a nivel de dosel", "frecuencia": "Permanente, cambiar cada 2–3 semanas", "disponible_veracruz": True},
            {"nombre": "Rotación de cultivos", "tipo": "cultural", "descripcion": "Rompe el ciclo de vida del trips. Alternar con cultivos no hospederos.", "aplicacion": "Planificación entre ciclos agrícolas", "frecuencia": "Por ciclo", "disponible_veracruz": True},
        ],
    },
    "minador": {
        "nombre_cientifico": "Liriomyza trifolii / Liriomyza sativae",
        "descripcion_plaga": "La larva excava galerías sinuosas dentro del tejido de la hoja (minas), reduciendo la fotosíntesis y favoreciendo infecciones secundarias.",
        "cultivos_afectados": ["Jitomate", "Chile", "Apio", "Lechuga", "Frijol"],
        "severidad_default": "Media",
        "mitigacion_viable": True,
        "nota_mitigacion": None,
        "tratamientos": [
            {"nombre": "Diglyphus isaea (parasitoide)", "tipo": "biologico", "descripcion": "Microavispa que parasita las larvas dentro de las galerías.", "aplicacion": "Liberación de adultos: 1 por m² en focos de infestación", "frecuencia": "Cada 2 semanas, 2–3 liberaciones", "disponible_veracruz": True},
            {"nombre": "Trampas amarillas adhesivas", "tipo": "fisico", "descripcion": "Captura adultos antes de que ovipositen.", "aplicacion": "4–6 trampas por cada 100 m²", "frecuencia": "Permanente", "disponible_veracruz": True},
            {"nombre": "Eliminación de hojas minadas", "tipo": "cultural", "descripcion": "Retirar y destruir hojas con galerías activas para reducir la población larval.", "aplicacion": "Poda y quema o bolsa sellada. No compostar.", "frecuencia": "Al detectar los primeros síntomas y semanalmente", "disponible_veracruz": True},
            {"nombre": "Extracto de neem", "tipo": "botanico", "descripcion": "Efecto antialimentario y repelente sobre adultos.", "aplicacion": "3 mL/L. Aspersión foliar completa.", "frecuencia": "Cada 7 días", "disponible_veracruz": True},
        ],
    },
    "gusano_cogollero": {
        "nombre_cientifico": "Spodoptera frugiperda",
        "descripcion_plaga": "Lepidóptero polífago de alta importancia en Veracruz. Las larvas atacan el cogollo del maíz causando daño severo. Una de las plagas más destructivas del estado.",
        "cultivos_afectados": ["Maíz", "Sorgo", "Chile", "Jitomate", "Caña de Azúcar"],
        "severidad_default": "Alta",
        "mitigacion_viable": True,
        "nota_mitigacion": "Actuar en los primeros 3 instares larvales. En poblaciones masivas la mitigación ecológica puede ser insuficiente.",
        "tratamientos": [
            {"nombre": "Bacillus thuringiensis (Bt)", "tipo": "biologico", "descripcion": "Bacteria que produce toxinas letales para larvas de lepidópteros. Específico e inocuo para otros organismos.", "aplicacion": "1–2 g/L. Aplicar directo al cogollo en horas frescas.", "frecuencia": "Cada 5–7 días mientras haya larvas jóvenes", "disponible_veracruz": True},
            {"nombre": "Metarhizium anisopliae", "tipo": "biologico", "descripcion": "Hongo entomopatógeno eficaz contra larvas en suelo y planta.", "aplicacion": "Aspersión foliar y al suelo: 2–5 kg/ha de producto comercial", "frecuencia": "Cada 10–15 días", "disponible_veracruz": True},
            {"nombre": "Arena o tierra de diatomeas en cogollo", "tipo": "fisico", "descripcion": "Abrasivo natural que daña la cutícula de larvas jóvenes.", "aplicacion": "Aplicar directamente en el cogollo con embudo o aspersor", "frecuencia": "Después de cada lluvia o riego", "disponible_veracruz": True},
            {"nombre": "Trampas con feromonas", "tipo": "fisico", "descripcion": "Captura de adultos macho para reducir reproducción. Clave para monitoreo.", "aplicacion": "1 trampa/ha en campo abierto", "frecuencia": "Permanente, revisar semanalmente", "disponible_veracruz": True},
        ],
    },
    "cochinilla": {
        "nombre_cientifico": "Planococcus citri / Pseudococcus longispinus",
        "descripcion_plaga": "Insecto escama harinoso que coloniza tallos, hojas y frutos. Produce melaza y cera blanca característica. Afecta especialmente cítricos en Veracruz.",
        "cultivos_afectados": ["Limón Persa", "Naranja", "Plátano", "Aguacate", "Vainilla"],
        "severidad_default": "Media",
        "mitigacion_viable": True,
        "nota_mitigacion": None,
        "tratamientos": [
            {"nombre": "Cryptolaemus montrouzieri (catarina depredadora)", "tipo": "biologico", "descripcion": "Coleóptero depredador especializado en cochinillas harinosas.", "aplicacion": "Liberación de adultos: 5–10 por planta infestada", "frecuencia": "Una liberación, evaluar a las 3 semanas", "disponible_veracruz": True},
            {"nombre": "Alcohol isopropílico + jabón", "tipo": "fisico", "descripcion": "Elimina la cera protectora y deshidrata a las cochinillas por contacto.", "aplicacion": "Algodón empapado o aspersión localizada sobre colonias", "frecuencia": "Cada 5 días hasta eliminar colonias visibles", "disponible_veracruz": True},
            {"nombre": "Aceite de Neem", "tipo": "botanico", "descripcion": "Penetra la cera y afecta la reproducción y muda.", "aplicacion": "5 mL/L + jabón potásico. Aspersión directa.", "frecuencia": "Cada 7 días, 3–4 aplicaciones", "disponible_veracruz": True},
            {"nombre": "Poda de partes afectadas", "tipo": "cultural", "descripcion": "Eliminar ramas y frutos con colonias densas para reducir la fuente de infestación.", "aplicacion": "Corte limpio, desinfectar tijeras entre plantas", "frecuencia": "Al detectar focos severos", "disponible_veracruz": True},
        ],
    },
    "roya": {
        "nombre_cientifico": "Hemileia vastatrix (café) / Phakopsora pachyrhizi",
        "descripcion_plaga": "Hongo foliar que produce pústulas de color naranja-café en el envés de hojas. En Veracruz afecta principalmente café en las zonas de Coatepec, Huatusco y Córdoba.",
        "cultivos_afectados": ["Café", "Frijol", "Soya", "Trigo"],
        "severidad_default": "Alta",
        "mitigacion_viable": True,
        "nota_mitigacion": "En cafetales con más del 30% de hojas infectadas, la mitigación ecológica debe complementarse con renovación de plantas.",
        "tratamientos": [
            {"nombre": "Caldo Bordelés (sulfato de cobre + cal)", "tipo": "botanico", "descripcion": "Fungicida cúprico de contacto. Protector y curativo en etapas tempranas.", "aplicacion": "10 g CuSO4 + 10 g cal / L agua. Aspersión foliar completa.", "frecuencia": "Preventiva cada 15 días en temporada de lluvia", "disponible_veracruz": True},
            {"nombre": "Trichoderma harzianum", "tipo": "biologico", "descripcion": "Hongo antagonista que compite e inhibe el desarrollo de la roya.", "aplicacion": "Aspersión foliar: solución 10⁸ esporas/mL", "frecuencia": "Cada 15 días como preventivo", "disponible_veracruz": True},
            {"nombre": "Poda sanitaria", "tipo": "cultural", "descripcion": "Eliminar ramas y hojas infectadas para reducir la fuente de inóculo.", "aplicacion": "Retirar material en bolsas selladas. No compostar.", "frecuencia": "Al detectar primeros síntomas y tras lluvias fuertes", "disponible_veracruz": True},
            {"nombre": "Variedades resistentes", "tipo": "cultural", "descripcion": "Renovar cafetales con variedades resistentes como Costa Rica 95 o Marsellesa.", "aplicacion": "Sustitución progresiva de plantas susceptibles", "frecuencia": "Por ciclo productivo", "disponible_veracruz": True},
        ],
    },
    "mildiu": {
        "nombre_cientifico": "Plasmopara viticola / Peronospora spp.",
        "descripcion_plaga": "Hongo oomiceto que produce manchas amarillas en el haz y moho blanco-grisáceo en el envés. Favorecido por alta humedad y temperaturas de 15–25°C.",
        "cultivos_afectados": ["Pepino", "Lechuga", "Espinaca", "Albahaca", "Uva"],
        "severidad_default": "Media",
        "mitigacion_viable": True,
        "nota_mitigacion": "Evitar riego nocturno. La humedad foliar prolongada es el principal factor de riesgo.",
        "tratamientos": [
            {"nombre": "Caldo Bordelés", "tipo": "botanico", "descripcion": "Fungicida cúprico eficaz contra oomicetos. Protector preventivo.", "aplicacion": "10 g CuSO4 + 10 g cal / L. Aspersión al haz y envés.", "frecuencia": "Preventiva cada 10–14 días en temporada húmeda", "disponible_veracruz": True},
            {"nombre": "Bicarbonato de sodio + jabón", "tipo": "botanico", "descripcion": "Altera el pH superficial de la hoja inhibiendo la germinación de esporas.", "aplicacion": "10 g bicarbonato + 5 mL jabón / L agua. Aspersión foliar.", "frecuencia": "Cada 5–7 días como preventivo", "disponible_veracruz": True},
            {"nombre": "Mejora de ventilación", "tipo": "cultural", "descripcion": "Reducir la densidad de siembra y podar hojas basales para mejorar circulación de aire.", "aplicacion": "Poda de aclareo y distanciamiento entre plantas", "frecuencia": "Al inicio del ciclo y según crecimiento", "disponible_veracruz": True},
            {"nombre": "Riego por goteo (no aspersión)", "tipo": "cultural", "descripcion": "Mantener el follaje seco reduce dramáticamente la incidencia de mildiu.", "aplicacion": "Cambiar de aspersión a goteo subterráneo o a la base", "frecuencia": "Permanente", "disponible_veracruz": True},
        ],
    },
    "mancha_foliar": {
        "nombre_cientifico": "Alternaria spp. / Cercospora spp. / Septoria spp.",
        "descripcion_plaga": "Complejo de hongos que producen manchas necróticas de distintas formas y colores en hojas. Favorecido por humedad y heridas. Puede confundirse visualmente con araña roja en etapas tempranas.",
        "cultivos_afectados": ["Jitomate", "Chile", "Maíz", "Frijol", "Café"],
        "severidad_default": "Baja",
        "mitigacion_viable": True,
        "nota_mitigacion": "Si el modelo indica mancha foliar pero los síntomas son punteado plateado fino con telarañas, revisar también araña roja (síntomas similares en foto).",
        "tratamientos": [
            {"nombre": "Trichoderma harzianum + Bacillus subtilis", "tipo": "biologico", "descripcion": "Antagonistas fúngicos que inhiben el crecimiento de patógenos foliares.", "aplicacion": "Aspersión foliar al atardecer. Mezcla comercial o casera.", "frecuencia": "Cada 10–15 días preventivo; cada 7 días en infección activa", "disponible_veracruz": True},
            {"nombre": "Caldo Bordelés", "tipo": "botanico", "descripcion": "Fungicida cúprico de amplio espectro para hongos foliares.", "aplicacion": "10 g CuSO4 + 10 g cal / L. Aspersión completa.", "frecuencia": "Cada 10–14 días", "disponible_veracruz": True},
            {"nombre": "Eliminación de hojas enfermas", "tipo": "cultural", "descripcion": "Retirar y destruir el material infectado para cortar el ciclo de esporas.", "aplicacion": "Poda con tijera desinfectada. Bolsa sellada para desecho.", "frecuencia": "Al detectar primeros síntomas y semanalmente", "disponible_veracruz": True},
            {"nombre": "Extracto de cola de caballo", "tipo": "botanico", "descripcion": "Rico en sílice. Refuerza la pared celular de las hojas contra infecciones fúngicas.", "aplicacion": "Hervir 100 g en 1 L agua, diluir 1:5 y asperjar.", "frecuencia": "Cada 5–7 días como preventivo", "disponible_veracruz": True},
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_severidad(confianza: float, plaga: str) -> str:
    """Determina severidad combinando confianza del modelo y naturaleza de la plaga."""
    plagas_alta = {"gusano_cogollero", "mosca_blanca", "roya", "arana_roja"}
    plagas_media = {"trips", "pulgon_verde", "minador", "mildiu", "cochinilla"}
    plagas_baja = {"mancha_foliar"}

    if plaga in plagas_alta:
        return "Alta" if confianza > 0.60 else "Media"
    elif plaga in plagas_media:
        return "Media" if confianza > 0.60 else "Baja"
    else:
        return "Baja"


def _detectar_mock(image_bytes: bytes) -> tuple[str, float]:
    """Mock determinista: mismos bytes → misma plaga. Para demos sin modelo."""
    clases = list(YOLO_CLASSES.values())
    digest = hashlib.sha256(image_bytes).hexdigest()
    idx = int(digest, 16) % len(clases)
    conf_seed = int(hashlib.sha256(image_bytes + b"conf").hexdigest(), 16)
    confianza = round(0.72 + (conf_seed % 27) / 100, 2)
    return clases[idx], confianza


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/detectar",
    response_model=DetectarResponse,
    summary="IA — Detecta plaga en imagen y devuelve tratamientos ecológicos",
)
async def detectar_plaga(
    imagen: UploadFile = File(
        ...,
        description="Archivo de imagen del cultivo (JPG, PNG o WebP). Máximo 10 MB.",
    ),
    huerto_id: Optional[str] = Form(default=None, description="ID del huerto (opcional)"),
    cultivo_id: Optional[str] = Form(default=None, description="ID del cultivo (opcional)"),
    current_user: dict = Depends(get_current_user),
):
    """
    Analiza un archivo de imagen de cultivo con YOLOv8n y detecta la plaga presente.

    Envía la imagen directamente como **multipart/form-data** (campo `imagen`).
    No requiere subir previamente la imagen a una URL externa.

    - **imagen**: Archivo de imagen adjunto (multipart/form-data).
    - Retorna la plaga detectada (de 10 clases entrenadas con datos de Veracruz),
      confianza, severidad y **tratamientos ecológicos específicos**.
    - Activa automáticamente el modelo real si `best.pt` existe en `/app/models/ml/`.
    - En modo mock: detección determinista basada en el hash del contenido del archivo.

    **Clases del modelo:** mosca_blanca, pulgon_verde, arana_roja, trips,
    minador, gusano_cogollero, cochinilla, roya, mildiu, mancha_foliar.

    **Formatos aceptados:** JPG, JPEG, PNG, WebP (máx. 10 MB).
    """
    content_type = (imagen.content_type or "").lower()
    ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
    if content_type and content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: '{content_type}'. Formatos permitidos: JPG, PNG, WebP.",
        )

    image_bytes = await imagen.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="El archivo de imagen está vacío.")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La imagen excede el límite máximo de 10 MB.")

    modo = "mock"
    modelo_version = "mock-v1.0"
    plaga_nombre = ""
    confianza = 0.0
    nombre_archivo = imagen.filename or "imagen_subida"

    # ── MODELO REAL ──────────────────────────────────────────────────────────
    model_path = os.path.abspath(MODEL_PATH)
    if os.path.exists(model_path):
        try:
            from ultralytics import YOLO

            ext = ".jpg"
            if "png" in content_type:
                ext = ".png"
            elif "webp" in content_type:
                ext = ".webp"

            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(image_bytes)
                tmp_path = f.name

            # Inferencia
            model = YOLO(model_path)
            results = model(tmp_path, verbose=False)
            os.unlink(tmp_path)

            if results and len(results) > 0:
                result = results[0]
                if hasattr(result, "probs") and result.probs is not None:
                    top1_idx = int(result.probs.top1)
                    plaga_nombre = YOLO_CLASSES.get(top1_idx, "mancha_foliar")
                    confianza = round(float(result.probs.top1conf), 2)
                elif hasattr(result, "boxes") and result.boxes is not None and len(result.boxes) > 0:
                    best_box = max(result.boxes, key=lambda b: float(b.conf))
                    plaga_nombre = YOLO_CLASSES.get(int(best_box.cls), "mancha_foliar")
                    confianza = round(float(best_box.conf), 2)
                else:
                    plaga_nombre = "mancha_foliar"
                    confianza = 0.51

            modo = "modelo_real"
            modelo_version = "yolov8n-veracruz-v1.0 (best.pt)"

        except Exception as exc:
            plaga_nombre, confianza = _detectar_mock(image_bytes)
            modo = f"mock (error en modelo: {type(exc).__name__})"
            modelo_version = "mock-v1.0"

    # ── MOCK ─────────────────────────────────────────────────────────────────
    if not plaga_nombre:
        plaga_nombre, confianza = _detectar_mock(image_bytes)

    # Obtener datos de la plaga
    datos = _TRATAMIENTOS_DB.get(plaga_nombre, _TRATAMIENTOS_DB["mancha_foliar"])
    severidad = _get_severidad(confianza, plaga_nombre)
    alerta = severidad in ("Alta", "Critica")

    tratamientos = [TratamientoEcologico(**t) for t in datos["tratamientos"]]

    return DetectarResponse(
        deteccion=DeteccionResult(
            plaga=plaga_nombre.replace("_", " ").title(),
            nombre_cientifico=datos["nombre_cientifico"],
            confianza=confianza,
            severidad=severidad,
            descripcion_plaga=datos["descripcion_plaga"],
            cultivos_afectados=datos["cultivos_afectados"],
            tratamientos_ecologicos=tratamientos,
            alerta_recomendada=alerta,
            mitigacion_viable=datos["mitigacion_viable"],
            nota_mitigacion=datos.get("nota_mitigacion"),
        ),
        imagen_analizada=nombre_archivo,
        modelo_version=modelo_version,
        modo=modo,
        mensaje=(
            "Modelo YOLOv8n activo — dataset veracruz_real (10 clases)."
            if modo == "modelo_real"
            else "Modo mock activo. Coloca best.pt en plagas-service/app/models/ml/ para activar el modelo real."
        ),
    )
