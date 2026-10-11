"""
Huertos Service — Huertos CRUD routes.
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.schemas import (
    HuertoCreate,
    HuertoResponse,
    HuertoUpdate,
    MessageResponse,
)
from shared.auth.dependencies import get_current_user, require_roles
from shared.ownership import require_huerto_access, object_id
from shared.regions import resolve_region

router = APIRouter(prefix="/api/huertos", tags=["Huertos"])


def _serialize_huerto(h: dict) -> HuertoResponse:
    return HuertoResponse(
        id=str(h["_id"]),
        nombre=h["nombre"],
        usuario_id=str(h.get("usuario_id", "")),
        municipio=h.get("municipio", ""),
        region_id=str(h["region_id"]) if h.get("region_id") else None,
        region=h.get("region"),
        estado=h.get("estado", "Optimo"),
        salud=h.get("salud", 100),
        created_at=h.get("created_at", "").isoformat() if h.get("created_at") else None,
    )


@router.get("", response_model=list[HuertoResponse])
async def list_huertos(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    region_id: str | None = None,
    region: str | None = Query(None, description="Nombre de región, por ejemplo Capital"),
    estado: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """List only the caller's active huertos, regardless of role."""
    db = request.app.state.mongodb

    query: dict = {"deleted_at": None}

    # Usuario role: only own huertos
    query["usuario_id"] = {"$in": [current_user["id"], object_id(current_user["id"])]}

    if region or region_id:
        selected = await resolve_region(db, region or region_id)
        query["region_id"] = {"$in": [str(selected["_id"]), selected["_id"]]}
    if estado:
        query["estado"] = estado

    cursor = db.huertos.find(query).sort("_id", -1).skip(skip).limit(limit)
    huertos = await cursor.to_list(limit)
    return [_serialize_huerto(h) for h in huertos]


@router.get("/{huerto_id}", response_model=HuertoResponse)
async def get_huerto(huerto_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Get a specific huerto."""
    db = request.app.state.mongodb
    h = await require_huerto_access(db, huerto_id, current_user)
    if not h:
        raise HTTPException(status_code=404, detail="Huerto no encontrado")

    # Check ownership for Usuario role
    if current_user["rol"] == "Usuario" and str(h.get("usuario_id")) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    return _serialize_huerto(h)


@router.post("", response_model=HuertoResponse, status_code=201)
async def create_huerto(
    body: HuertoCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Create a new huerto. Assigned to the current user."""
    db = request.app.state.mongodb

    # Only Admin, Tecnico, and Usuario can create
    if current_user["rol"] not in ["Admin", "Tecnico", "Usuario"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    now = datetime.now(timezone.utc)
    selected = await resolve_region(db, body.region or body.region_id) if body.region or body.region_id else None
    if body.region and body.region_id and str(selected["_id"]) != body.region_id:
        raise HTTPException(422, "region y region_id no coinciden")
    doc = {
        "nombre": body.nombre,
        "usuario_id": ObjectId(current_user["id"]),
        "municipio": body.municipio,
        "region_id": str(selected["_id"]) if selected else None,
        "region": selected["nombre"] if selected else None,
        "estado": body.estado,
        "salud": body.salud,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    result = await db.huertos.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize_huerto(doc)


@router.put("/{huerto_id}", response_model=HuertoResponse)
async def update_huerto(
    huerto_id: str,
    body: HuertoUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update a huerto."""
    db = request.app.state.mongodb

    h = await require_huerto_access(db, huerto_id, current_user)
    if not h:
        raise HTTPException(status_code=404, detail="Huerto no encontrado")

    # Check ownership for Usuario role
    if current_user["rol"] == "Usuario" and str(h.get("usuario_id")) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")

    update_data["updated_at"] = datetime.now(timezone.utc)
    if body.region or body.region_id:
        selected = await resolve_region(db, body.region or body.region_id)
        if body.region and body.region_id and str(selected["_id"]) != body.region_id:
            raise HTTPException(422, "region y region_id no coinciden")
        update_data.update(region_id=str(selected["_id"]), region=selected["nombre"])
    await db.huertos.update_one({"_id": ObjectId(huerto_id)}, {"$set": update_data})

    h = await db.huertos.find_one({"_id": ObjectId(huerto_id)})
    return _serialize_huerto(h)


@router.delete("/{huerto_id}", response_model=MessageResponse)
async def delete_huerto(
    huerto_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Soft-delete a huerto."""
    db = request.app.state.mongodb

    h = await require_huerto_access(db, huerto_id, current_user)
    if not h:
        raise HTTPException(status_code=404, detail="Huerto no encontrado")

    # Check ownership for Usuario role
    if current_user["rol"] == "Usuario" and str(h.get("usuario_id")) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    now = datetime.now(timezone.utc)
    await db.huertos.update_one(
        {"_id": ObjectId(huerto_id)},
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    return MessageResponse(message="Huerto eliminado")
