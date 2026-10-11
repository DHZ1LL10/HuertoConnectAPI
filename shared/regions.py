"""Official Veracruz planning regions (SEFIPLAN), with name-based lookup."""
import re
import unicodedata

from bson import ObjectId
from fastapi import HTTPException

VERACRUZ_REGIONS = (
    "Huasteca Alta", "Huasteca Baja", "Totonaca", "Nautla", "Capital",
    "Las Montañas", "Sotavento", "Papaloapan", "Los Tuxtlas", "Olmeca",
)
REGIONS_SOURCE = "https://www.veracruz.gob.mx/finanzas/estudios-regionales-para-la-planeacion/erp-2020/"


def region_key(value):
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    return " ".join("".join(c for c in normalized if not unicodedata.combining(c)).split())


async def resolve_region(db, value):
    if ObjectId.is_valid(value):
        region = await db.regiones.find_one({"_id": ObjectId(value)})
    else:
        key = region_key(value)
        key = {"totonacapan": "totonaca", "montanas": "las montanas"}.get(key, key)
        canonical = next((name for name in VERACRUZ_REGIONS if region_key(name) == key), value.strip())
        region = await db.regiones.find_one({"nombre": {"$regex": "^" + re.escape(canonical) + "$", "$options": "i"}})
    if not region:
        raise HTTPException(404, "Región no encontrada; consulta GET /api/regiones")
    return region


async def seed_regions(db):
    """Idempotent, non-destructive seed; old catalog removal is an explicit migration."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    await db.regiones.create_index("nombre", unique=True)
    for name in VERACRUZ_REGIONS:
        await db.regiones.update_one({"nombre": name}, {"$setOnInsert": {
            "nombre": name, "actividad": "Media", "priorizada": False,
            "created_at": now, "updated_at": now, "fuente": REGIONS_SOURCE,
        }}, upsert=True)
