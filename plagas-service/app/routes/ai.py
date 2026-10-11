import io
import logging
import warnings
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ConfigDict
from starlette.concurrency import run_in_threadpool

from app.ai.model_manager import ModelUnavailable, ModelBusy
from app.ai.plague_classifier import ImageClassifier
from app.ai.yield_predictor import YieldPredictor
from shared.auth.dependencies import get_current_user
from shared.ownership import require_huerto_access
from shared.config import settings

router = APIRouter(prefix="/ai", tags=["IA V6"])
logger = logging.getLogger(__name__)


class TopClass(BaseModel):
    clase: str
    confianza: float


class Classification(BaseModel):
    tipo: str
    detectado: bool
    clase: str
    confianza: float
    margen: float
    top: list[TopClass]
    modelo: str
    version: str
    nota: str
    diagnostico_id: str | None = None
    imagen_url: str | None = None
    imagen_file_id: str | None = None
    recomendaciones: list[str] = Field(default_factory=list, description="Orientación preventiva, no un tratamiento confirmado")


class YieldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, json_schema_extra={"example": {
        "Anio": 2026, "Nommunicipio": "Xalapa", "Nomcultivo": "Maíz grano",
        "Nomcicloproductivo": "Primavera-Verano", "Nommodalidad": "Temporal",
    }})
    Anio: int = Field(ge=2000, le=2100, strict=True)
    Nommunicipio: str = Field(min_length=1)
    Nomcultivo: str = Field(min_length=1)
    Nomcicloproductivo: str = Field(min_length=1)
    Nommodalidad: str = Field(min_length=1)


def decode_image(data, content_type):
    formats = {"image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    if content_type not in formats:
        raise HTTPException(415, "Formatos permitidos: JPG, JPEG, PNG y WebP")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != formats[content_type] or image.width * image.height > 25_000_000:
                    raise ValueError()
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Imagen inválida, demasiado grande o MIME incorrecto")


async def classify(request, kind, imagen, huerto_id, user, guardar_imagen=False):
    if huerto_id:
        await require_huerto_access(request.app.state.mongodb, huerto_id, user)
    data = await imagen.read(settings.AI_MAX_IMAGE_BYTES + 1)
    if len(data) > settings.AI_MAX_IMAGE_BYTES:
        raise HTTPException(413, f"La imagen excede {settings.AI_MAX_IMAGE_BYTES} bytes")
    image = await run_in_threadpool(decode_image, data, imagen.content_type)
    try:
        result = await run_in_threadpool(ImageClassifier(request.app.state.models, kind).predict, image)
    except ModelBusy:
        raise HTTPException(429, "Modelo ocupado; intenta de nuevo", headers={"Retry-After": "2"})
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        logger.error("inference_failed kind=%s error=%s", kind, type(exc).__name__)
        raise HTTPException(503, "No fue posible ejecutar el modelo")
    finally:
        image.close()
    result["recomendaciones"] = (
        ["Toma otra foto nítida con buena luz y revisa ambas caras de la hoja.",
         "No apliques tratamientos basándote en esta clasificación incierta."]
        if not result["detectado"] else
        ["Revisa otras hojas y plantas para confirmar la extensión de los síntomas.",
         "Evita trasladar material afectado a plantas sanas; limpia las herramientas.",
         "Consulta a una persona agrónoma para confirmar la causa antes de aplicar productos."]
    )
    if guardar_imagen:
        from shared.services.image_storage import upload_image
        try:
            stored = await upload_image(data, folder=f"huerto-connect/diagnosticos/{user['id']}")
        except RuntimeError:
            raise HTTPException(502, "No fue posible almacenar la imagen")
        result["imagen_url"] = stored["secure_url"]
        result["imagen_file_id"] = stored["public_id"]
    if huerto_id:
        doc = {**result, "usuario_id": user["id"], "huerto_id": huerto_id, "fecha": datetime.now(timezone.utc)}
        saved = await request.app.state.mongodb.diagnosticos.insert_one(doc)
        result["diagnostico_id"] = str(saved.inserted_id)
    return result


@router.post("/plagas/predict", response_model=Classification, summary="Subir foto y clasificar plaga con orientación preventiva", responses={413: {}, 415: {}, 422: {}, 429: {}, 502: {}, 503: {}})
async def plague(request: Request, imagen: UploadFile = File(..., description="Selecciona una foto JPG, PNG o WebP"), huerto_id: str | None = Form(None), guardar_imagen: bool = Form(False, description="Guardar también la foto en ImageKit"), user=Depends(get_current_user)):
    """Clasifica la imagen completa; guarda diagnóstico si se proporciona un huerto propio."""
    return await classify(request, "plaga", imagen, huerto_id, user, guardar_imagen)


@router.post("/enfermedades/predict", response_model=Classification, summary="Subir foto y clasificar enfermedad con orientación preventiva", responses={413: {}, 415: {}, 422: {}, 429: {}, 502: {}, 503: {}})
async def disease(request: Request, imagen: UploadFile = File(..., description="Selecciona una foto JPG, PNG o WebP"), huerto_id: str | None = Form(None), guardar_imagen: bool = Form(False, description="Guardar también la foto en ImageKit"), user=Depends(get_current_user)):
    return await classify(request, "enfermedad", imagen, huerto_id, user, guardar_imagen)


@router.get("/{tipo}/classes")
async def classes(tipo: Literal["plagas", "enfermedades"], request: Request, user=Depends(get_current_user)):
    try:
        kind = "plaga" if tipo == "plagas" else "enfermedad"
        return {"clases": request.app.state.models.require(kind).names, "metadata": request.app.state.models.metadata.get(kind, {})}
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc))


@router.get("/health")
async def health(request: Request):
    models = request.app.state.models.health()
    ok = all(m["loaded"] for m in models.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "models": models}, status_code=200 if ok else 503)


@router.post("/rendimiento/predict", tags=["Random Forest — Rendimiento"], summary="Predecir rendimiento agrícola con Random Forest", responses={422: {}, 503: {}})
async def yield_prediction(body: YieldRequest, request: Request, user=Depends(get_current_user)):
    """Predice rendimiento histórico, no clima ni el cultivo ideal. Consulta primero /ai/rendimiento/opciones para usar categorías del artefacto real."""
    try:
        return await run_in_threadpool(YieldPredictor(request.app.state.models).predict, body.model_dump())
    except ModelBusy:
        raise HTTPException(429, "Modelo ocupado; intenta de nuevo", headers={"Retry-After": "2"})
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        raise HTTPException(503, "No fue posible ejecutar el modelo de rendimiento")


@router.get("/rendimiento/opciones", tags=["Random Forest — Rendimiento"], summary="Consultar municipios, cultivos, ciclos y modalidades admitidos")
async def yield_options(request: Request, user=Depends(get_current_user)):
    try:
        return await run_in_threadpool(YieldPredictor(request.app.state.models).options)
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc))


@router.get("/diagnosticos/{huerto_id}")
async def history(huerto_id: str, request: Request, user=Depends(get_current_user), skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=200)):
    await require_huerto_access(request.app.state.mongodb, huerto_id, user)
    docs = await request.app.state.mongodb.diagnosticos.find({"huerto_id": huerto_id, "usuario_id": user["id"]}).sort([("fecha", -1), ("_id", -1)]).skip(skip).limit(limit).to_list(limit)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs
