"""
Reportes Service — FastAPI Application
Microservice for reportes and auditoría logs.
Uses PostgreSQL via SQLAlchemy async + MongoDB for auth session validation.
"""

import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, select, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.database import (
    Base,
    connect_mongodb,
    close_mongodb,
    get_postgres_engine,
    get_session_factory,
    init_postgres_tables,
)
from shared.auth.dependencies import get_current_user, require_roles


# ===================== MODELS =====================

class Reporte(Base):
    __tablename__ = "reportes"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(300), nullable=False)
    tipo = Column(String(100), nullable=False)
    estado = Column(String(20), nullable=False, default="En_proceso")
    archivo_url = Column(String(500))
    generado_por = Column(String(100), nullable=False)
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditoriaLog(Base):
    __tablename__ = "auditoria_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(String(100), nullable=False)
    accion = Column(String(200), nullable=False)
    modulo = Column(String(100), nullable=False)
    ip = Column(String(50))
    detalle_json = Column(Text)
    fecha = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ===================== SCHEMAS =====================

class ReporteCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=300)
    tipo: str = Field(min_length=1, max_length=100)
    archivo_url: Optional[HttpUrl] = None

    @field_validator("archivo_url")
    @classmethod
    def no_credentials(cls, value):
        if value and (value.username or value.password):
            raise ValueError("La URL no debe contener credenciales")
        return value

    model_config = {
        "extra": "forbid", "str_strip_whitespace": True,
        "json_schema_extra": {
            "example": {
                "nombre": "Reporte semanal de plagas - Zona Norte",
                "tipo": "pdf",
                "archivo_url": "https://storage.huertoconnect.com/reportes/reporte_plagas_semana12.pdf",
            }
        }
    }


class ReporteResponse(BaseModel):
    id: str
    nombre: str
    tipo: str
    estado: str
    archivo_url: Optional[str] = None
    generado_por: str
    fecha: Optional[str] = None


class AuditoriaLogResponse(BaseModel):
    id: str
    actor_id: str
    accion: str
    modulo: str
    ip: Optional[str] = None
    detalle_json: Optional[str] = None
    fecha: Optional[str] = None


class MessageResponse(BaseModel):
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Reporte eliminado",
            }
        }
    }


# ===================== DB SESSION =====================

async def get_db(request: Request, user: dict = Depends(get_current_user)) -> AsyncSession:
    async with request.app.state.session_factory() as session:
        from shared.sql_ownership import restrict_session
        restrict_session(session, [(Reporte, "generado_por", [user["id"]])])
        yield session


# ===================== REPORTES ROUTES =====================

reportes_router = APIRouter(prefix="/api/reportes", tags=["Reportes"])


@reportes_router.get("", response_model=list[ReporteResponse])
async def list_reportes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    estado: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """List reportes."""
    query = select(Reporte)
    if estado:
        query = query.where(Reporte.estado == estado)
    query = query.order_by(Reporte.fecha.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()
    return [
        ReporteResponse(
            id=str(r.id), nombre=r.nombre, tipo=r.tipo,
            estado=r.estado, archivo_url=r.archivo_url,
            generado_por=r.generado_por,
            fecha=r.fecha.isoformat() if r.fecha else None,
        )
        for r in items
    ]


@reportes_router.post("", response_model=ReporteResponse, status_code=201)
async def create_reporte(
    body: ReporteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create a new reporte."""
    reporte = Reporte(
        nombre=body.nombre, tipo=body.tipo,
        archivo_url=str(body.archivo_url) if body.archivo_url else None,
        estado="Generado" if body.archivo_url else "En_proceso",
        generado_por=current_user["id"],
    )
    db.add(reporte)
    await db.flush()
    db.add(AuditoriaLog(actor_id=current_user["id"], accion="crear_reporte", modulo="reportes", detalle_json=json.dumps({"reporte_id": str(reporte.id)})))
    await db.commit()
    await db.refresh(reporte)
    return ReporteResponse(
        id=str(reporte.id), nombre=reporte.nombre, tipo=reporte.tipo,
        estado=reporte.estado, archivo_url=reporte.archivo_url,
        generado_por=reporte.generado_por,
        fecha=reporte.fecha.isoformat() if reporte.fecha else None,
    )


@reportes_router.delete("/{reporte_id}", response_model=MessageResponse)
async def delete_reporte(
    reporte_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """Delete a reporte."""
    result = await db.execute(select(Reporte).where(Reporte.id == reporte_id))
    reporte = result.scalar_one_or_none()
    if not reporte:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    await db.delete(reporte)
    db.add(AuditoriaLog(actor_id=current_user["id"], accion="eliminar_reporte", modulo="reportes", detalle_json=json.dumps({"reporte_id": str(reporte_id)})))
    await db.commit()
    return MessageResponse(message="Reporte eliminado")


# ===================== AUDITORIA ROUTES =====================

auditoria_router = APIRouter(prefix="/api/auditoria", tags=["Auditoría"])


@auditoria_router.get("", response_model=list[AuditoriaLogResponse])
async def list_auditoria(
    actor_id: Optional[str] = None,
    modulo: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """List audit logs — Admin only."""
    query = select(AuditoriaLog)
    if actor_id:
        query = query.where(AuditoriaLog.actor_id == actor_id)
    if modulo:
        query = query.where(AuditoriaLog.modulo == modulo)

    query = query.order_by(AuditoriaLog.fecha.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    return [
        AuditoriaLogResponse(
            id=str(a.id), actor_id=a.actor_id, accion=a.accion,
            modulo=a.modulo, ip=a.ip, detalle_json=a.detalle_json,
            fecha=a.fecha.isoformat() if a.fecha else None,
        )
        for a in items
    ]


# ===================== APP =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = None
    try:
        app.state.mongodb = await connect_mongodb()
        await app.state.mongodb.reporte_exportaciones.create_index([("usuario_id", 1), ("huerto_id", 1), ("fecha", -1)])
        engine = get_postgres_engine()
        app.state.engine = engine
        app.state.session_factory = get_session_factory(engine)
        await init_postgres_tables(engine)
        yield
    finally:
        if engine is not None:
            await engine.dispose()
        await close_mongodb()


app = FastAPI(
    title="Huerto Connect — Reportes Service",
    description="Microservicio de reportes y auditoría",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Report-Total", "X-Report-Records", "X-Report-Truncated"],
)

app.include_router(reportes_router)
app.include_router(auditoria_router)
from app.export import router as export_router
app.include_router(export_router)
from shared.observability import install_observability
install_observability(app, "reportes")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "reportes-service"}

@app.get("/health/live", tags=["Health"])
async def live():
    return {"status": "ok", "service": "reportes-service"}


@app.get("/health/ready", tags=["Health"])
async def ready():
    checks = {"mongodb": False, "postgres": False}
    try:
        async with asyncio.timeout(5):
            await app.state.mongodb.command("ping")
            checks["mongodb"] = True
            async with app.state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception:
        pass
    ok = all(checks.values())
    return JSONResponse({"status": "ok" if ok else "unavailable", "dependencies": checks}, status_code=200 if ok else 503)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse({"detail": "Conflicto al guardar el reporte"}, status_code=409)
