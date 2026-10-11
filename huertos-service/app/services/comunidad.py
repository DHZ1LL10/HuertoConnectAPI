"""Community persistence, visibility, cursor paging and lightweight summaries."""
from datetime import datetime, timezone

from fastapi import HTTPException

from shared.ownership import object_id
from shared.regions import VERACRUZ_REGIONS, region_key


def now():
    return datetime.now(timezone.utc)


def author(user):
    return {"id": user["id"], "nombre": " ".join(filter(None, [user.get("nombre"), user.get("apellidos")])).strip() or "Usuario"}


def is_admin(user):
    return user.get("rol") == "Admin"


def canonical_region(value):
    if value is None:
        return None
    key = region_key(value)
    key = {"totonacapan": "totonaca", "montanas": "las montanas"}.get(key, key)
    name = next((name for name in VERACRUZ_REGIONS if region_key(name) == key), None)
    if not name:
        raise HTTPException(422, "Región no válida; consulta GET /api/comunidad/opciones")
    return name


async def init_indexes(db):
    posts = db.comunidad_publicaciones
    await posts.create_index([("deleted_at", 1), ("estado", 1), ("_id", -1)])
    await posts.create_index([("deleted_at", 1), ("estado", 1), ("region", 1), ("_id", -1)])
    await posts.create_index([("deleted_at", 1), ("estado", 1), ("cultivo_key", 1), ("_id", -1)])
    await posts.create_index([("autor.id", 1), ("created_at", -1)])
    await db.comunidad_comentarios.create_index([("publicacion_id", 1), ("deleted_at", 1), ("estado", 1), ("_id", -1)])
    await db.comunidad_comentarios.create_index([("autor.id", 1), ("created_at", -1)])
    await db.comunidad_me_gusta.create_index([("publicacion_id", 1), ("usuario_id", 1)], unique=True)


async def rate_limit(collection, user, limit):
    from datetime import timedelta
    count = await collection.count_documents({"autor.id": user["id"], "created_at": {"$gt": now() - timedelta(minutes=1)}})
    if count >= limit:
        raise HTTPException(429, "Demasiadas publicaciones o comentarios; espera un minuto", headers={"Retry-After": "60"})


async def post_for_user(db, post_id, user, *, writable=False):
    query = {"_id": object_id(post_id), "deleted_at": None}
    if writable:
        query["estado"] = "Publicada"
    doc = await db.comunidad_publicaciones.find_one(query)
    if not doc or (doc["estado"] != "Publicada" and doc["autor"]["id"] != user["id"] and not is_admin(user)):
        raise HTTPException(404, "Publicación no encontrada")
    return doc


def owner_only(doc, user):
    if doc["autor"]["id"] != user["id"]:
        raise HTTPException(403, "Solo el autor puede modificar este contenido")


async def page(collection, query, cursor, limit, projection=None):
    query = dict(query)
    if cursor:
        query["_id"] = {"$lt": object_id(cursor)}
    docs = await collection.find(query, projection).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    more = len(docs) > limit
    docs = docs[:limit]
    return docs, str(docs[-1]["_id"]) if more else None, more


async def summaries(db, docs, user, *, photos=False, detail=False):
    ids = [str(doc["_id"]) for doc in docs]
    if not ids:
        return []
    async def totals(collection, extra=None):
        query = {"publicacion_id": {"$in": ids}, **(extra or {})}
        pipeline = [{"$match": query}, {"$group": {"_id": "$publicacion_id", "total": {"$sum": 1}}}]
        return {row["_id"]: row["total"] async for row in collection.aggregate(pipeline)}
    likes = await totals(db.comunidad_me_gusta)
    comments = await totals(db.comunidad_comentarios, {"deleted_at": None, "estado": "Publicada"})
    own_likes = {row["publicacion_id"] async for row in db.comunidad_me_gusta.find({"publicacion_id": {"$in": ids}, "usuario_id": user["id"]}, {"publicacion_id": 1})}
    output = []
    for doc in docs:
        post_id = str(doc["_id"])
        item = {"id": post_id, "autor": doc["autor"], "titulo": doc["titulo"],
                "resumen": doc["contenido"][:240], "tipo": doc["tipo"],
                "region": doc.get("region"), "cultivo": doc.get("cultivo"), "estado": doc["estado"],
                "fotos": [{"id": f["id"], "url": f["url"]} for f in doc.get("fotos", [])] if photos else [],
                "total_fotos": len(doc.get("fotos", [])), "total_comentarios": comments.get(post_id, 0),
                "total_me_gusta": likes.get(post_id, 0), "me_gusta": post_id in own_likes,
                "created_at": doc["created_at"], "updated_at": doc["updated_at"]}
        if detail:
            item["contenido"] = doc["contenido"]
        output.append(item)
    return output


def comment_response(doc):
    return {"id": str(doc["_id"]), **{key: doc[key] for key in ("publicacion_id", "autor", "contenido", "estado", "created_at", "updated_at")}}


async def moderate(collection, content_id, body, user):
    timestamp = now()
    event = {"estado": body.estado, "motivo": body.motivo, "moderado_por": user["id"], "fecha": timestamp}
    result = await collection.update_one({"_id": object_id(content_id), "deleted_at": None}, {
        "$set": {"estado": body.estado, "updated_at": timestamp},
        "$push": {"moderacion": {"$each": [event], "$slice": -20}},
    })
    if not result.matched_count:
        raise HTTPException(404, "Contenido no encontrado")
    return {"id": content_id, "estado": body.estado, "motivo": body.motivo, "moderado_por": user["id"], "updated_at": timestamp}
