"""
Reportes Service — FastAPI Application
Microservice for reportes and auditoría logs.
Uses PostgreSQL via SQLAlchemy async + MongoDB for auth session validation.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text, select, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

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
    nombre: str = Field(..., min_length=1)
    tipo: str
    archivo_url: Optional[str] = None

    model_config = {
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

async def get_db(request: Request) -> AsyncSession:
    async with request.app.state.session_factory() as session:
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
        archivo_url=body.archivo_url,
        generado_por=current_user["id"],
    )
    db.add(reporte)
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
    reporte_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """Delete a reporte."""
    result = await db.execute(select(Reporte).where(Reporte.id == uuid.UUID(reporte_id)))
    reporte = result.scalar_one_or_none()
    if not reporte:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    await db.delete(reporte)
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
    print("📊 Reportes Service starting...")

    # MongoDB for auth session validation
    db = await connect_mongodb()
    app.state.mongodb = db
    print("  ✅ Connected to MongoDB (auth sessions)")

    # PostgreSQL for reportes data
    engine = get_postgres_engine()
    app.state.engine = engine
    app.state.session_factory = get_session_factory(engine)
    await init_postgres_tables(engine)
    print("  ✅ Connected to PostgreSQL (reportes data)")

    port = 8005
    print(f"  📖 Swagger UI: http://localhost:{port}/docs")
    print(f"📊 Reportes Service ready on port {port}")

    yield

    await engine.dispose()
    await close_mongodb()
    print("📊 Reportes Service stopped.")


app = FastAPI(
    title="Huerto Connect — Reportes Service",
    description="Microservicio de reportes y auditoría",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reportes_router)
app.include_router(auditoria_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "reportes-service"}
