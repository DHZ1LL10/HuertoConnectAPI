"""
Plagas Service — Routes for plagas, alertas, dashboard, modelos IA, predicciones, datasets, recomendaciones.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Alerta,
    Dataset,
    ModeloIA,
    PlagaDeteccion,
    Prediccion,
    RecomendacionCultivo,
)
from app.models.schemas import (
    AlertaCreate,
    AlertaResponse,
    AlertaUpdate,
    DashboardKPIs,
    DatasetCreate,
    DatasetResponse,
    MessageResponse,
    ModeloIACreate,
    ModeloIAResponse,
    PlagaDeteccionCreate,
    PlagaDeteccionResponse,
    PlagaDeteccionUpdate,
    PrediccionCreate,
    PrediccionFeedback,
    PrediccionResponse,
    RecomendacionCreate,
    RecomendacionResponse,
)
from shared.auth.dependencies import get_current_user, require_roles


async def get_db(request: Request) -> AsyncSession:
    """Get database session from request state."""
    async with request.app.state.session_factory() as session:
        yield session


async def _create_notification(
    request: Request,
    usuario_id: str | None,
    *,
    titulo: str,
    mensaje: str,
    tipo: str = "alerta",
    referencia_id: str | None = None,
    referencia_tipo: str | None = "alerta",
) -> None:
    """Persist a user notification in MongoDB without breaking main flow."""
    if not usuario_id:
        return

    db = request.app.state.mongodb
    try:
        user_oid = ObjectId(usuario_id)
    except Exception:
        return

    user = await db.usuarios.find_one({"_id": user_oid, "deleted_at": None})
    if not user:
        return

    now = datetime.now(timezone.utc)
    await db.notificaciones_usuario.insert_one(
        {
            "usuario_id": usuario_id,
            "titulo": titulo,
            "mensaje": mensaje,
            "tipo": tipo,
            "leida": False,
            "referencia_id": referencia_id,
            "referencia_tipo": referencia_tipo,
            "fecha": now,
            "created_at": now,
            "updated_at": now,
        }
    )


# ===================== PLAGAS =====================

plagas_router = APIRouter(prefix="/api/plagas", tags=["Plagas"])


@plagas_router.get("", response_model=list[PlagaDeteccionResponse])
async def list_plagas(
    huerto_id: Optional[str] = None,
    severidad: Optional[str] = None,
    estado: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List plaga detecciones with filters."""
    query = select(PlagaDeteccion)
    if huerto_id:
        query = query.where(PlagaDeteccion.huerto_id == huerto_id)
    if severidad:
        query = query.where(PlagaDeteccion.severidad == severidad)
    if estado:
        query = query.where(PlagaDeteccion.estado == estado)

    query = query.order_by(PlagaDeteccion.fecha.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        PlagaDeteccionResponse(
            id=str(p.id), imagen_url=p.imagen_url, plaga=p.plaga,
            confianza=float(p.confianza) if p.confianza else 0,
            huerto_id=p.huerto_id, cultivo_id=p.cultivo_id,
            severidad=p.severidad, estado=p.estado,
            fecha=p.fecha.isoformat() if p.fecha else None,
        )
        for p in items
    ]


@plagas_router.post("", response_model=PlagaDeteccionResponse, status_code=201)
async def create_plaga(
    body: PlagaDeteccionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create a plaga detection record."""
    det = PlagaDeteccion(
        imagen_url=body.imagen_url, plaga=body.plaga,
        confianza=body.confianza, huerto_id=body.huerto_id,
        cultivo_id=body.cultivo_id, severidad=body.severidad,
        estado=body.estado,
    )
    db.add(det)
    await db.commit()
    await db.refresh(det)
    return PlagaDeteccionResponse(
        id=str(det.id), imagen_url=det.imagen_url, plaga=det.plaga,
        confianza=float(det.confianza) if det.confianza else 0,
        huerto_id=det.huerto_id, cultivo_id=det.cultivo_id,
        severidad=det.severidad, estado=det.estado,
        fecha=det.fecha.isoformat() if det.fecha else None,
    )


from pydantic import BaseModel

class ImageUploadResponse(BaseModel):
    secure_url: str
    public_id: str
    message: str


@plagas_router.post("/upload-imagen", response_model=ImageUploadResponse, status_code=201)
async def upload_plaga_imagen(
    request: Request,
    imagen: UploadFile = File(..., description="Foto de la plaga detectada (JPG/PNG/WebP, máx 5 MB)"),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """
    Sube una imagen de plaga a Cloudinary y devuelve la URL y el public_id.

    Usa la URL devuelta como ``imagen_url`` al crear un registro en
    ``POST /api/plagas``. El ``public_id`` permite transformaciones y borrado.

    - Formatos permitidos: JPG, PNG, WebP (máx 5 MB).
    - Acceso: Admin o Técnico.
    """
    ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_EXT  = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_BYTES    = 5 * 1024 * 1024  # 5 MB

    filename = imagen.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    content_type = imagen.content_type or ""

    if ext not in ALLOWED_EXT or content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no permitido '{ext}'. Usa JPG, PNG o WebP.",
        )

    file_bytes = await imagen.read()
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera el límite de 5 MB.",
        )

    try:
        from shared.services.cloudinary_service import upload_image
        uid = str(uuid.uuid4())[:8]
        cloud_result = await upload_image(
            file_bytes,
            folder="huerto-connect/plagas",
            public_id=f"plaga_{uid}",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ImageUploadResponse(
        secure_url=cloud_result["secure_url"],
        public_id=cloud_result["public_id"],
        message="Imagen subida correctamente. Usa secure_url en POST /api/plagas.",
    )


@plagas_router.patch("/{plaga_id}", response_model=PlagaDeteccionResponse)
async def update_plaga(
    plaga_id: str,
    body: PlagaDeteccionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Update a plaga detection."""
    result = await db.execute(select(PlagaDeteccion).where(PlagaDeteccion.id == uuid.UUID(plaga_id)))
    det = result.scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="Detección no encontrada")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    for key, value in update_data.items():
        setattr(det, key, value)

    await db.commit()
    await db.refresh(det)
    return PlagaDeteccionResponse(
        id=str(det.id), imagen_url=det.imagen_url, plaga=det.plaga,
        confianza=float(det.confianza) if det.confianza else 0,
        huerto_id=det.huerto_id, cultivo_id=det.cultivo_id,
        severidad=det.severidad, estado=det.estado,
        fecha=det.fecha.isoformat() if det.fecha else None,
    )


@plagas_router.delete("/{plaga_id}", response_model=MessageResponse)
async def delete_plaga(
    plaga_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Delete a plaga detection."""
    result = await db.execute(delete(PlagaDeteccion).where(PlagaDeteccion.id == uuid.UUID(plaga_id)))
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=404, detail="Detección no encontrada")
    await db.commit()
    return MessageResponse(message="Detección eliminada")


# ===================== ALERTAS =====================

alertas_router = APIRouter(prefix="/api/alertas", tags=["Alertas"])


@alertas_router.get("", response_model=list[AlertaResponse])
async def list_alertas(
    huerto_id: Optional[str] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List alertas with filters."""
    query = select(Alerta)
    if huerto_id:
        query = query.where(Alerta.huerto_id == huerto_id)
    if tipo:
        query = query.where(Alerta.tipo == tipo)
    if estado:
        query = query.where(Alerta.estado == estado)

    query = query.order_by(Alerta.fecha.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        AlertaResponse(
            id=str(a.id), titulo=a.titulo, tipo=a.tipo,
            severidad=a.severidad, estado=a.estado,
            huerto_id=a.huerto_id, responsable_id=a.responsable_id,
            fecha=a.fecha.isoformat() if a.fecha else None,
            resuelta_en=a.resuelta_en.isoformat() if a.resuelta_en else None,
        )
        for a in items
    ]


@alertas_router.post("", response_model=AlertaResponse, status_code=201)
async def create_alerta(
    body: AlertaCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create an alerta."""
    alerta = Alerta(
        titulo=body.titulo, tipo=body.tipo,
        severidad=body.severidad, huerto_id=body.huerto_id,
        responsable_id=body.responsable_id,
    )
    db.add(alerta)
    await db.commit()
    await db.refresh(alerta)

    target_user_id = body.responsable_id or current_user["id"]
    await _create_notification(
        request,
        target_user_id,
        titulo=f"Nueva alerta: {alerta.titulo}",
        mensaje=(
            f"Se creó una alerta de tipo {alerta.tipo} con severidad {alerta.severidad} "
            f"para el huerto {alerta.huerto_id}."
        ),
        tipo="alerta",
        referencia_id=str(alerta.id),
    )

    return AlertaResponse(
        id=str(alerta.id), titulo=alerta.titulo, tipo=alerta.tipo,
        severidad=alerta.severidad, estado=alerta.estado,
        huerto_id=alerta.huerto_id, responsable_id=alerta.responsable_id,
        fecha=alerta.fecha.isoformat() if alerta.fecha else None,
        resuelta_en=None,
    )


@alertas_router.patch("/{alerta_id}", response_model=AlertaResponse)
async def update_alerta(
    alerta_id: str,
    body: AlertaUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Update an alerta."""
    result = await db.execute(select(Alerta).where(Alerta.id == uuid.UUID(alerta_id)))
    alerta = result.scalar_one_or_none()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if update_data.get("estado") == "Resuelta":
        update_data["resuelta_en"] = datetime.now(timezone.utc)

    for key, value in update_data.items():
        setattr(alerta, key, value)

    await db.commit()
    await db.refresh(alerta)

    # Notify the responsible user (or actor) on key alerta lifecycle changes.
    if update_data.get("estado"):
        target_user_id = alerta.responsable_id or current_user["id"]
        await _create_notification(
            request,
            target_user_id,
            titulo=f"Alerta actualizada: {alerta.titulo}",
            mensaje=(
                f"La alerta cambió a estado {alerta.estado} "
                f"con severidad {alerta.severidad}."
            ),
            tipo="alerta",
            referencia_id=str(alerta.id),
        )

    if update_data.get("responsable_id"):
        await _create_notification(
            request,
            update_data["responsable_id"],
            titulo=f"Alerta asignada: {alerta.titulo}",
            mensaje=(
                f"Se te asignó una alerta de tipo {alerta.tipo} "
                f"para el huerto {alerta.huerto_id}."
            ),
            tipo="info",
            referencia_id=str(alerta.id),
        )

    return AlertaResponse(
        id=str(alerta.id), titulo=alerta.titulo, tipo=alerta.tipo,
        severidad=alerta.severidad, estado=alerta.estado,
        huerto_id=alerta.huerto_id, responsable_id=alerta.responsable_id,
        fecha=alerta.fecha.isoformat() if alerta.fecha else None,
        resuelta_en=alerta.resuelta_en.isoformat() if alerta.resuelta_en else None,
    )


@alertas_router.delete("/{alerta_id}", response_model=MessageResponse)
async def delete_alerta(
    alerta_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Delete an alerta."""
    result = await db.execute(delete(Alerta).where(Alerta.id == uuid.UUID(alerta_id)))
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    await db.commit()
    return MessageResponse(message="Alerta eliminada")


# ===================== DASHBOARD =====================

dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@dashboard_router.get("/kpis", response_model=DashboardKPIs)
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Get dashboard KPIs from PostgreSQL data."""
    total_det = (await db.execute(select(func.count(PlagaDeteccion.id)))).scalar() or 0
    confirmadas = (await db.execute(
        select(func.count(PlagaDeteccion.id)).where(PlagaDeteccion.estado == "Confirmada")
    )).scalar() or 0
    alertas_ab = (await db.execute(
        select(func.count(Alerta.id)).where(Alerta.estado == "Abierta")
    )).scalar() or 0
    alertas_crit = (await db.execute(
        select(func.count(Alerta.id)).where(Alerta.severidad == "Critico", Alerta.estado != "Resuelta")
    )).scalar() or 0
    modelos_act = (await db.execute(
        select(func.count(ModeloIA.id)).where(ModeloIA.estado == "activo")
    )).scalar() or 0
    pred_total = (await db.execute(select(func.count(Prediccion.id)))).scalar() or 0
    avg_prec = (await db.execute(
        select(func.avg(ModeloIA.precision_score)).where(ModeloIA.estado == "activo")
    )).scalar()

    return DashboardKPIs(
        total_detecciones=total_det,
        detecciones_confirmadas=confirmadas,
        alertas_abiertas=alertas_ab,
        alertas_criticas=alertas_crit,
        modelos_activos=modelos_act,
        predicciones_totales=pred_total,
        precision_promedio=float(avg_prec) if avg_prec else None,
    )


# ===================== MODELOS IA =====================

modelos_router = APIRouter(prefix="/api/modelos", tags=["Modelos IA"])


@modelos_router.get("", response_model=list[ModeloIAResponse])
async def list_modelos(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """List AI models."""
    result = await db.execute(
        select(ModeloIA).order_by(ModeloIA.created_at.desc()).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    return [
        ModeloIAResponse(
            id=str(m.id), nombre=m.nombre, version=m.version, tipo=m.tipo,
            arquitectura=m.arquitectura,
            precision_score=float(m.precision_score) if m.precision_score else None,
            recall_score=float(m.recall_score) if m.recall_score else None,
            f1_score=float(m.f1_score) if m.f1_score else None,
            estado=m.estado,
            fecha_entrenamiento=m.fecha_entrenamiento.isoformat() if m.fecha_entrenamiento else None,
            created_at=m.created_at.isoformat() if m.created_at else None,
        )
        for m in items
    ]


@modelos_router.post("", response_model=ModeloIAResponse, status_code=201)
async def create_modelo(
    body: ModeloIACreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Register a new AI model."""
    modelo = ModeloIA(
        nombre=body.nombre, version=body.version, tipo=body.tipo,
        arquitectura=body.arquitectura, ruta_archivo=body.ruta_archivo,
        parametros_json=body.parametros_json,
    )
    db.add(modelo)
    await db.commit()
    await db.refresh(modelo)
    return ModeloIAResponse(
        id=str(modelo.id), nombre=modelo.nombre, version=modelo.version,
        tipo=modelo.tipo, arquitectura=modelo.arquitectura,
        estado=modelo.estado,
        created_at=modelo.created_at.isoformat() if modelo.created_at else None,
    )


# ===================== PREDICCIONES =====================

predicciones_router = APIRouter(prefix="/api/predicciones", tags=["Predicciones"])


@predicciones_router.get("", response_model=list[PrediccionResponse])
async def list_predicciones(
    huerto_id: Optional[str] = None,
    cultivo_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List AI predictions with optional huerto/cultivo filters."""
    query = select(Prediccion)
    if huerto_id:
        query = query.where(Prediccion.huerto_id == huerto_id)
    if cultivo_id:
        query = query.where(Prediccion.cultivo_id == cultivo_id)

    query = query.order_by(Prediccion.fecha.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        PrediccionResponse(
            id=str(p.id),
            modelo_id=str(p.modelo_id),
            imagen_url=p.imagen_url,
            huerto_id=p.huerto_id,
            plaga_predicha=p.plaga_predicha,
            confianza=float(p.confianza) if p.confianza else None,
            severidad_predicha=p.severidad_predicha,
            resultado_real=p.resultado_real,
            correcto=p.correcto,
            latencia_ms=p.latencia_ms,
            fecha=p.fecha.isoformat() if p.fecha else None,
        )
        for p in items
    ]


@predicciones_router.post("", response_model=PrediccionResponse, status_code=201)
async def create_prediccion(
    body: PrediccionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Record a prediction from an AI model."""
    pred = Prediccion(
        modelo_id=uuid.UUID(body.modelo_id),
        imagen_url=body.imagen_url, huerto_id=body.huerto_id,
        cultivo_id=body.cultivo_id, plaga_predicha=body.plaga_predicha,
        confianza=body.confianza, severidad_predicha=body.severidad_predicha,
        latencia_ms=body.latencia_ms,
    )
    db.add(pred)
    await db.commit()
    await db.refresh(pred)
    return PrediccionResponse(
        id=str(pred.id), modelo_id=str(pred.modelo_id),
        imagen_url=pred.imagen_url, huerto_id=pred.huerto_id,
        plaga_predicha=pred.plaga_predicha,
        confianza=float(pred.confianza) if pred.confianza else None,
        severidad_predicha=pred.severidad_predicha,
        latencia_ms=pred.latencia_ms,
        fecha=pred.fecha.isoformat() if pred.fecha else None,
    )


@predicciones_router.patch("/{pred_id}/feedback", response_model=MessageResponse)
async def feedback_prediccion(
    pred_id: str,
    body: PrediccionFeedback,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Provide feedback on a prediction (feedback loop)."""
    result = await db.execute(select(Prediccion).where(Prediccion.id == uuid.UUID(pred_id)))
    pred = result.scalar_one_or_none()
    if not pred:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")

    pred.resultado_real = body.resultado_real
    pred.correcto = body.correcto
    await db.commit()
    return MessageResponse(message="Feedback registrado")


# ===================== DATASETS =====================

datasets_router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


@datasets_router.get("", response_model=list[DatasetResponse])
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """List training datasets."""
    result = await db.execute(select(Dataset).order_by(Dataset.fecha_creacion.desc()))
    items = result.scalars().all()
    return [
        DatasetResponse(
            id=str(d.id), nombre=d.nombre, descripcion=d.descripcion,
            tipo=d.tipo, total_imagenes=d.total_imagenes,
            clases_json=d.clases_json, version=d.version,
            fecha_creacion=d.fecha_creacion.isoformat() if d.fecha_creacion else None,
        )
        for d in items
    ]


@datasets_router.post("", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    body: DatasetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create a training dataset record."""
    ds = Dataset(
        nombre=body.nombre, descripcion=body.descripcion, tipo=body.tipo,
        total_imagenes=body.total_imagenes, clases_json=body.clases_json,
        ruta_almacenamiento=body.ruta_almacenamiento, version=body.version,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return DatasetResponse(
        id=str(ds.id), nombre=ds.nombre, descripcion=ds.descripcion,
        tipo=ds.tipo, total_imagenes=ds.total_imagenes,
        clases_json=ds.clases_json, version=ds.version,
        fecha_creacion=ds.fecha_creacion.isoformat() if ds.fecha_creacion else None,
    )


# ===================== RECOMENDACIONES =====================

recomendaciones_router = APIRouter(prefix="/api/recomendaciones", tags=["Recomendaciones"])


@recomendaciones_router.get("", response_model=list[RecomendacionResponse])
async def list_recomendaciones(
    huerto_id: Optional[str] = None,
    tipo: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List AI recommendations. Users see only their own huerto recommendations."""
    query = select(RecomendacionCultivo)
    if huerto_id:
        query = query.where(RecomendacionCultivo.huerto_id == huerto_id)
    if tipo:
        query = query.where(RecomendacionCultivo.tipo_recomendacion == tipo)

    query = query.order_by(RecomendacionCultivo.fecha.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        RecomendacionResponse(
            id=str(r.id), huerto_id=r.huerto_id, cultivo_id=r.cultivo_id,
            modelo_id=str(r.modelo_id) if r.modelo_id else None,
            tipo_recomendacion=r.tipo_recomendacion,
            descripcion=r.descripcion,
            confianza=float(r.confianza) if r.confianza else None,
            aceptada=r.aceptada,
            fecha=r.fecha.isoformat() if r.fecha else None,
        )
        for r in items
    ]


@recomendaciones_router.post("", response_model=RecomendacionResponse, status_code=201)
async def create_recomendacion(
    body: RecomendacionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create an AI recommendation."""
    rec = RecomendacionCultivo(
        huerto_id=body.huerto_id, cultivo_id=body.cultivo_id,
        modelo_id=uuid.UUID(body.modelo_id) if body.modelo_id else None,
        tipo_recomendacion=body.tipo_recomendacion,
        descripcion=body.descripcion, confianza=body.confianza,
        parametros_entrada_json=body.parametros_entrada_json,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return RecomendacionResponse(
        id=str(rec.id), huerto_id=rec.huerto_id, cultivo_id=rec.cultivo_id,
        modelo_id=str(rec.modelo_id) if rec.modelo_id else None,
        tipo_recomendacion=rec.tipo_recomendacion,
        descripcion=rec.descripcion,
        confianza=float(rec.confianza) if rec.confianza else None,
        aceptada=rec.aceptada,
        fecha=rec.fecha.isoformat() if rec.fecha else None,
    )


@recomendaciones_router.patch("/{rec_id}/aceptar", response_model=MessageResponse)
async def aceptar_recomendacion(
    rec_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Accept or reject an AI recommendation."""
    result = await db.execute(
        select(RecomendacionCultivo).where(RecomendacionCultivo.id == uuid.UUID(rec_id))
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recomendación no encontrada")

    rec.aceptada = True
    await db.commit()
    return MessageResponse(message="Recomendación aceptada")
