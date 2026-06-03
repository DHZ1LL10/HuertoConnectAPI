"""
Huertos Service — Cultivos CRUD routes.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.schemas import (
    CultivoCreate,
    CultivoResponse,
    CultivoUpdate,
    HuertoCultivoCreate,
    HuertoCultivoResponse,
    MessageResponse,
)
from shared.auth.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/api/cultivos", tags=["Cultivos"])


@router.get("", response_model=list[CultivoResponse])
async def list_cultivos(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    activo: bool | None = None,
    current_user: dict = Depends(get_current_user),
):
    """List all cultivos."""
    db = request.app.state.mongodb
    query = {}
    if activo is not None:
        query["activo"] = activo

    cursor = db.cultivos.find(query).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    return [
        CultivoResponse(
            id=str(c["_id"]),
            nombre=c["nombre"],
            temporada=c.get("temporada", ""),
            dificultad=c.get("dificultad", "Media"),
            riego=c.get("riego", ""),
            fertilizacion=c.get("fertilizacion", ""),
            activo=c.get("activo", True),
            created_at=c.get("created_at", "").isoformat() if c.get("created_at") else None,
        )
        for c in items
    ]


@router.post("", response_model=CultivoResponse, status_code=201)
async def create_cultivo(
    body: CultivoCreate,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create a new cultivo."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    doc = {
        "nombre": body.nombre,
        "temporada": body.temporada,
        "dificultad": body.dificultad,
        "riego": body.riego,
        "fertilizacion": body.fertilizacion,
        "activo": body.activo,
        "created_at": now,
    }
    result = await db.cultivos.insert_one(doc)
    doc["_id"] = result.inserted_id
    return CultivoResponse(
        id=str(doc["_id"]),
        nombre=doc["nombre"],
        temporada=doc["temporada"],
        dificultad=doc["dificultad"],
        riego=doc["riego"],
        fertilizacion=doc["fertilizacion"],
        activo=doc["activo"],
        created_at=now.isoformat(),
    )


@router.put("/{cultivo_id}", response_model=CultivoResponse)
async def update_cultivo(
    cultivo_id: str,
    body: CultivoUpdate,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Update a cultivo."""
    db = request.app.state.mongodb
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")

    result = await db.cultivos.update_one({"_id": ObjectId(cultivo_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")

    c = await db.cultivos.find_one({"_id": ObjectId(cultivo_id)})
    return CultivoResponse(
        id=str(c["_id"]),
        nombre=c["nombre"],
        temporada=c.get("temporada", ""),
        dificultad=c.get("dificultad", "Media"),
        riego=c.get("riego", ""),
        fertilizacion=c.get("fertilizacion", ""),
        activo=c.get("activo", True),
        created_at=c.get("created_at", "").isoformat() if c.get("created_at") else None,
    )


@router.delete("/{cultivo_id}", response_model=MessageResponse)
async def delete_cultivo(
    cultivo_id: str,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """Delete a cultivo."""
    db = request.app.state.mongodb
    result = await db.cultivos.delete_one({"_id": ObjectId(cultivo_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado")
    return MessageResponse(message="Cultivo eliminado")


# ===================== HUERTO-CULTIVOS (Siembras) =====================

@router.post("/siembras", response_model=HuertoCultivoResponse, status_code=201)
async def create_siembra(
    body: HuertoCultivoCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Link a cultivo to a huerto (siembra)."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    doc = {
        "huerto_id": body.huerto_id,
        "cultivo_id": body.cultivo_id,
        "fecha_siembra": body.fecha_siembra,
        "estado": body.estado,
        "created_at": now,
    }
    result = await db.huerto_cultivos.insert_one(doc)
    doc["_id"] = result.inserted_id
    return HuertoCultivoResponse(
        id=str(doc["_id"]),
        huerto_id=doc["huerto_id"],
        cultivo_id=doc["cultivo_id"],
        fecha_siembra=doc["fecha_siembra"],
        estado=doc["estado"],
        created_at=now.isoformat(),
    )


@router.get("/siembras/{huerto_id}", response_model=list[HuertoCultivoResponse])
async def list_siembras(
    huerto_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all siembras (huerto-cultivo links) for a huerto."""
    db = request.app.state.mongodb
    items = await db.huerto_cultivos.find({"huerto_id": huerto_id}).to_list(100)
    return [
        HuertoCultivoResponse(
            id=str(hc["_id"]),
            huerto_id=hc["huerto_id"],
            cultivo_id=hc["cultivo_id"],
            fecha_siembra=hc.get("fecha_siembra"),
            estado=hc.get("estado", "Activo"),
            created_at=hc.get("created_at", "").isoformat() if hc.get("created_at") else None,
        )
        for hc in items
    ]
