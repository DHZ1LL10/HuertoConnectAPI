"""
Huertos Service — Regiones CRUD routes.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.schemas import (
    MessageResponse,
    PlantioResponse,
    RegionCreate,
    RegionResponse,
    RegionUpdate,
)
from shared.auth.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/api/regiones", tags=["Regiones"])


@router.get("", response_model=list[RegionResponse])
async def list_regiones(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """List all regiones."""
    db = request.app.state.mongodb
    cursor = db.regiones.find().skip(skip).limit(limit)
    regiones = await cursor.to_list(limit)
    return [
        RegionResponse(
            id=str(r["_id"]),
            nombre=r["nombre"],
            actividad=r.get("actividad", "Media"),
            priorizada=r.get("priorizada", False),
            created_at=r.get("created_at", "").isoformat() if r.get("created_at") else None,
        )
        for r in regiones
    ]


@router.get("/{region_id}", response_model=RegionResponse)
async def get_region(region_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get a specific region."""
    db = request.app.state.mongodb
    r = await db.regiones.find_one({"_id": ObjectId(region_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Región no encontrada")
    return RegionResponse(
        id=str(r["_id"]),
        nombre=r["nombre"],
        actividad=r.get("actividad", "Media"),
        priorizada=r.get("priorizada", False),
        created_at=r.get("created_at", "").isoformat() if r.get("created_at") else None,
    )


@router.post("", response_model=RegionResponse, status_code=201)
async def create_region(
    body: RegionCreate,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Create a new region."""
    db = request.app.state.mongodb

    existing = await db.regiones.find_one({"nombre": body.nombre})
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe una región con ese nombre")

    now = datetime.now(timezone.utc)
    doc = {
        "nombre": body.nombre,
        "actividad": body.actividad,
        "priorizada": body.priorizada,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.regiones.insert_one(doc)
    doc["_id"] = result.inserted_id

    return RegionResponse(
        id=str(doc["_id"]),
        nombre=doc["nombre"],
        actividad=doc["actividad"],
        priorizada=doc["priorizada"],
        created_at=now.isoformat(),
    )


@router.put("/{region_id}", response_model=RegionResponse)
async def update_region(
    region_id: str,
    body: RegionUpdate,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Update a region."""
    db = request.app.state.mongodb
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")

    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await db.regiones.update_one({"_id": ObjectId(region_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Región no encontrada")

    r = await db.regiones.find_one({"_id": ObjectId(region_id)})
    return RegionResponse(
        id=str(r["_id"]),
        nombre=r["nombre"],
        actividad=r.get("actividad", "Media"),
        priorizada=r.get("priorizada", False),
        created_at=r.get("created_at", "").isoformat() if r.get("created_at") else None,
    )


@router.delete("/{region_id}", response_model=MessageResponse)
async def delete_region(
    region_id: str,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """Delete a region."""
    db = request.app.state.mongodb
    result = await db.regiones.delete_one({"_id": ObjectId(region_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Región no encontrada")
    return MessageResponse(message="Región eliminada")


@router.get("/{region_id}/plantios", response_model=list[PlantioResponse])
async def get_plantios_by_region(
    region_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get all plantíos within a region (via huertos)."""
    db = request.app.state.mongodb

    # Find huertos in this region
    huertos = await db.huertos.find(
        {"region_id": region_id, "deleted_at": None}
    ).to_list(500)
    huerto_ids = [str(h["_id"]) for h in huertos]

    # Find huerto_cultivos for these huertos
    hcs = await db.huerto_cultivos.find(
        {"huerto_id": {"$in": huerto_ids}}
    ).to_list(1000)
    hc_ids = [str(hc["_id"]) for hc in hcs]

    # Find plantios
    plantios = await db.plantios.find(
        {"huerto_cultivo_id": {"$in": hc_ids}}
    ).to_list(500)

    return [
        PlantioResponse(
            id=str(p["_id"]),
            nombre=p["nombre"],
            huerto_cultivo_id=p["huerto_cultivo_id"],
            municipio=p.get("municipio", ""),
            lat=p.get("lat", 0),
            lng=p.get("lng", 0),
            salud=p.get("salud", 100),
            severidad=p.get("severidad", "Baja"),
            created_at=p.get("created_at", "").isoformat() if p.get("created_at") else None,
        )
        for p in plantios
    ]
