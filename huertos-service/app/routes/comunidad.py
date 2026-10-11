"""Agricultural community, authenticated with existing API JWT sessions."""
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from app.models.comunidad import (
    ComentarioCreate, ComentarioResponse, ComentariosPagina, ComunidadMessage,
    FotoComunidad, HistorialModeracion, MeGustaResponse, ModeracionRequest, PublicacionCreate,
    PublicacionDetalle, PublicacionUpdate, PublicacionesPagina, ResultadoModeracion,
    TipoPublicacion,
)
from app.services import comunidad as service
from app.services.images import validate_image
from shared.auth.dependencies import get_current_user, require_roles
from shared.ownership import object_id
from shared.regions import VERACRUZ_REGIONS, region_key
from shared.services.image_storage import delete_image, upload_image

router = APIRouter(prefix="/api/comunidad",
                   responses={401: {"description": "Sesión requerida o revocada"}, 403: {"description": "Permiso insuficiente"}, 404: {"description": "Contenido no disponible"}, 429: {"description": "Límite temporal alcanzado"}})
logger = logging.getLogger("comunidad")


@router.get("/opciones", tags=["Comunidad — Opciones"], summary="Regiones y opciones de la comunidad")
async def options(user: dict = Depends(get_current_user)):
    return {"regiones": list(VERACRUZ_REGIONS), "tipos": ["Experiencia", "Pregunta", "Consejo"],
            "cultivo": "Nombre libre; el filtro ignora mayúsculas y acentos",
            "max_fotos": 4, "max_bytes_foto": 5 * 1024 * 1024,
            "formatos_foto": ["image/jpeg", "image/png", "image/webp"], "limite_pagina_default": 10, "limite_pagina_max": 50}


@router.get("/publicaciones", response_model=PublicacionesPagina, tags=["Comunidad — Publicaciones"], summary="Listar publicaciones con paginación y filtros")
async def list_posts(request: Request, cursor: str | None = Query(None, max_length=24),
                     limit: int = Query(10, ge=1, le=50), region: str | None = Query(None, min_length=1, max_length=80),
                     cultivo: str | None = Query(None, min_length=1, max_length=80), tipo: TipoPublicacion | None = None,
                     solo_mias: bool = False, incluir_ocultas: bool = False, incluir_fotos: bool = False,
                     user: dict = Depends(get_current_user)):
    """El cursor viene de `siguiente_cursor`; conserva los filtros entre páginas.

    Ocultas: solo tu propio contenido con `solo_mias=true`, o todo si eres Admin.
    Las fotos son URLs originales, nunca imágenes incorporadas al JSON.
    """
    db = request.app.state.mongodb
    query = {"deleted_at": None}
    if incluir_ocultas and not solo_mias and not service.is_admin(user):
        raise HTTPException(403, "Solo Admin puede consultar contenido oculto de otros usuarios")
    if not incluir_ocultas:
        query["estado"] = "Publicada"
    if solo_mias:
        query["autor.id"] = user["id"]
    if region is not None:
        query["region"] = service.canonical_region(region)
    if cultivo is not None:
        if not region_key(cultivo):
            raise HTTPException(422, "Cultivo no válido")
        query["cultivo_key"] = region_key(cultivo)
    if tipo:
        query["tipo"] = tipo
    docs, next_cursor, more = await service.page(db.comunidad_publicaciones, query, cursor, limit, {"moderacion": 0})
    return {"items": await service.summaries(db, docs, user, photos=incluir_fotos), "siguiente_cursor": next_cursor, "hay_mas": more}


@router.post("/publicaciones", response_model=PublicacionDetalle, status_code=201, tags=["Comunidad — Publicaciones"], summary="Crear publicación (primer paso; devuelve id)")
async def create_post(body: PublicacionCreate, request: Request, user: dict = Depends(get_current_user)):
    """Crea una experiencia, pregunta o consejo sin solicitar un identificador.

    Devuelve HTTP 201 con el campo `id`. Usa ese valor como `publicacion_id`
    para consultar, editar, agregar fotos o crear comentarios.
    """
    db = request.app.state.mongodb
    await service.rate_limit(db.comunidad_publicaciones, user, 5)
    timestamp = service.now()
    doc = {**body.model_dump(), "region": service.canonical_region(body.region),
           "cultivo_key": region_key(body.cultivo) if body.cultivo else None,
           "autor": service.author(user), "fotos": [], "estado": "Publicada", "deleted_at": None,
           "created_at": timestamp, "updated_at": timestamp}
    doc["_id"] = (await db.comunidad_publicaciones.insert_one(doc)).inserted_id
    return (await service.summaries(db, [doc], user, photos=True, detail=True))[0]


@router.get("/publicaciones/{publicacion_id}", response_model=PublicacionDetalle, tags=["Comunidad — Publicaciones"], summary="Consultar una publicación completa")
async def get_post(publicacion_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    doc = await service.post_for_user(db, publicacion_id, user)
    return (await service.summaries(db, [doc], user, photos=True, detail=True))[0]


@router.patch("/publicaciones/{publicacion_id}", response_model=PublicacionDetalle, tags=["Comunidad — Publicaciones"], summary="Editar una publicación propia")
async def edit_post(publicacion_id: str, body: PublicacionUpdate, request: Request, user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    doc = await service.post_for_user(db, publicacion_id, user, writable=True)
    service.owner_only(doc, user)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No hay cambios")
    if "region" in updates:
        updates["region"] = service.canonical_region(updates["region"])
    if "cultivo" in updates:
        updates["cultivo_key"] = region_key(updates["cultivo"]) if updates["cultivo"] else None
    updates["updated_at"] = service.now()
    result = await db.comunidad_publicaciones.update_one({"_id": doc["_id"], "estado": "Publicada", "deleted_at": None}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(409, "La publicación ya no está disponible para editar")
    return await get_post(publicacion_id, request, user)


@router.delete("/publicaciones/{publicacion_id}", response_model=ComunidadMessage, tags=["Comunidad — Publicaciones"], summary="Eliminar una publicación propia")
async def delete_post(publicacion_id: str, request: Request, user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    doc = await service.post_for_user(db, publicacion_id, user)
    service.owner_only(doc, user)
    await db.comunidad_publicaciones.update_one({"_id": doc["_id"], "deleted_at": None}, {"$set": {"deleted_at": service.now(), "updated_at": service.now()}})
    return {"message": "Publicación eliminada de la comunidad"}


@router.post("/publicaciones/{publicacion_id}/fotos", response_model=FotoComunidad, status_code=201,
             tags=["Comunidad — Fotos"], summary="Sube una foto original a ImageKit; máximo 4 por publicación",
             responses={413: {"description": "Foto mayor a 5 MiB"}, 415: {"description": "Formato no admitido"}, 422: {"description": "Foto inválida"}, 503: {"description": "Almacenamiento no disponible"}})
async def upload_photo(publicacion_id: str, request: Request, foto: UploadFile = File(...), user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    doc = await service.post_for_user(db, publicacion_id, user, writable=True)
    service.owner_only(doc, user)
    if len(doc.get("fotos", [])) >= 4:
        raise HTTPException(409, "La publicación ya tiene 4 fotos")
    try:
        if foto.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, "Solo se admiten JPEG, PNG y WebP")
        data = await foto.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "Foto mayor a 5 MiB; envía el original, no es necesario reducirlo automáticamente")
        await run_in_threadpool(validate_image, data, foto.content_type)
    finally:
        await foto.close()
    try:
        stored = await upload_image(data, folder=f"huerto_connect/comunidad/{publicacion_id}")
    except RuntimeError:
        raise HTTPException(503, "No fue posible guardar la foto en ImageKit; intenta de nuevo") from None
    photo = {"id": uuid.uuid4().hex, "url": stored["secure_url"], "file_id": stored["public_id"]}
    try:
        result = await db.comunidad_publicaciones.update_one({"_id": doc["_id"], "deleted_at": None, "estado": "Publicada", "fotos.3": {"$exists": False}},
                                                            {"$push": {"fotos": photo}, "$set": {"updated_at": service.now()}})
        if not result.matched_count:
            raise HTTPException(409, "La publicación cambió o alcanzó el límite de fotos")
    except Exception as error:
        try:
            await delete_image(stored["public_id"])
        except RuntimeError:
            logger.error("community_upload_rollback_failed")
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(503, "No fue posible asociar la foto a la publicación") from None
    return {"id": photo["id"], "url": photo["url"]}


@router.get("/publicaciones/{publicacion_id}/comentarios", response_model=ComentariosPagina, tags=["Comunidad — Comentarios"], summary="Comentarios paginados")
async def list_comments(publicacion_id: str, request: Request, cursor: str | None = Query(None, max_length=24),
                        limit: int = Query(10, ge=1, le=50), incluir_ocultos: bool = False, user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    await service.post_for_user(db, publicacion_id, user)
    if incluir_ocultos and not service.is_admin(user):
        raise HTTPException(403, "Solo Admin puede consultar comentarios ocultos")
    query = {"publicacion_id": publicacion_id, "deleted_at": None}
    if not incluir_ocultos:
        query["estado"] = "Publicada"
    docs, next_cursor, more = await service.page(db.comunidad_comentarios, query, cursor, limit, {"moderacion": 0})
    return {"items": [service.comment_response(doc) for doc in docs], "siguiente_cursor": next_cursor, "hay_mas": more}


@router.post("/publicaciones/{publicacion_id}/comentarios", response_model=ComentarioResponse, status_code=201,
             tags=["Comunidad — Comentarios"], summary="Crear comentario en una publicación (devuelve id)")
async def create_comment(publicacion_id: str, body: ComentarioCreate, request: Request, user: dict = Depends(get_current_user)):
    """Usa el `id` de POST /api/comunidad/publicaciones como `publicacion_id`.

    Devuelve HTTP 201 con el `id` del comentario. Usa ese nuevo identificador
    como `comentario_id` para editarlo o eliminarlo.
    """
    db = request.app.state.mongodb
    await service.post_for_user(db, publicacion_id, user, writable=True)
    await service.rate_limit(db.comunidad_comentarios, user, 20)
    timestamp = service.now()
    doc = {"publicacion_id": publicacion_id, "autor": service.author(user), "contenido": body.contenido,
           "estado": "Publicada", "deleted_at": None, "created_at": timestamp, "updated_at": timestamp}
    doc["_id"] = (await db.comunidad_comentarios.insert_one(doc)).inserted_id
    return service.comment_response(doc)


@router.patch("/comentarios/{comentario_id}", response_model=ComentarioResponse, tags=["Comunidad — Comentarios"], summary="Edita tu comentario")
async def edit_comment(comentario_id: str, body: ComentarioCreate, request: Request, user: dict = Depends(get_current_user)):
    db = request.app.state.mongodb
    doc = await db.comunidad_comentarios.find_one({"_id": object_id(comentario_id), "deleted_at": None, "estado": "Publicada"})
    if not doc:
        raise HTTPException(404, "Comentario no encontrado")
    service.owner_only(doc, user)
    await service.post_for_user(db, doc["publicacion_id"], user, writable=True)
    timestamp = service.now()
    result = await db.comunidad_comentarios.update_one({"_id": doc["_id"], "deleted_at": None, "estado": "Publicada"}, {"$set": {"contenido": body.contenido, "updated_at": timestamp}})
    if not result.matched_count:
        raise HTTPException(409, "El comentario ya no está disponible")
    doc.update(contenido=body.contenido, updated_at=timestamp)
    return service.comment_response(doc)


@router.delete("/comentarios/{comentario_id}", response_model=ComunidadMessage, tags=["Comunidad — Comentarios"], summary="Elimina tu comentario")
async def delete_comment(comentario_id: str, request: Request, user: dict = Depends(get_current_user)):
    collection = request.app.state.mongodb.comunidad_comentarios
    doc = await collection.find_one({"_id": object_id(comentario_id), "deleted_at": None})
    if not doc:
        raise HTTPException(404, "Comentario no encontrado")
    service.owner_only(doc, user)
    await collection.update_one({"_id": doc["_id"]}, {"$set": {"deleted_at": service.now(), "updated_at": service.now()}})
    return {"message": "Comentario eliminado"}


async def change_like(publicacion_id, request, user, enabled):
    db = request.app.state.mongodb
    await service.post_for_user(db, publicacion_id, user, writable=True)
    query = {"publicacion_id": publicacion_id, "usuario_id": user["id"]}
    if enabled:
        try:
            await db.comunidad_me_gusta.update_one(query, {"$setOnInsert": {**query, "created_at": service.now()}}, upsert=True)
        except DuplicateKeyError:
            pass  # Reintentos concurrentes son idempotentes gracias al índice único.
    else:
        await db.comunidad_me_gusta.delete_one(query)
    return {"publicacion_id": publicacion_id, "me_gusta": enabled,
            "total_me_gusta": await db.comunidad_me_gusta.count_documents({"publicacion_id": publicacion_id})}


@router.put("/publicaciones/{publicacion_id}/me-gusta", response_model=MeGustaResponse, tags=["Comunidad — Me gusta"], summary="Da me gusta; repetir no duplica")
async def like(publicacion_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await change_like(publicacion_id, request, user, True)


@router.delete("/publicaciones/{publicacion_id}/me-gusta", response_model=MeGustaResponse, tags=["Comunidad — Me gusta"], summary="Retira me gusta; repetir es seguro")
async def unlike(publicacion_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await change_like(publicacion_id, request, user, False)


@router.patch("/publicaciones/{publicacion_id}/moderacion", response_model=ResultadoModeracion, tags=["Comunidad — Moderación"], summary="Admin: oculta o restablece una publicación")
async def moderate_post(publicacion_id: str, body: ModeracionRequest, request: Request, user: dict = Depends(require_roles(["Admin"]))):
    return await service.moderate(request.app.state.mongodb.comunidad_publicaciones, publicacion_id, body, user)


@router.patch("/comentarios/{comentario_id}/moderacion", response_model=ResultadoModeracion, tags=["Comunidad — Moderación"], summary="Admin: oculta o restablece un comentario")
async def moderate_comment(comentario_id: str, body: ModeracionRequest, request: Request, user: dict = Depends(require_roles(["Admin"]))):
    return await service.moderate(request.app.state.mongodb.comunidad_comentarios, comentario_id, body, user)


@router.get("/moderacion/{tipo}/{contenido_id}", response_model=HistorialModeracion, tags=["Comunidad — Moderación"], summary="Admin: consulta las últimas 20 decisiones de moderación")
async def moderation_history(tipo: Literal["publicaciones", "comentarios"], contenido_id: str, request: Request, user: dict = Depends(require_roles(["Admin"]))):
    db = request.app.state.mongodb
    collection = db.comunidad_publicaciones if tipo == "publicaciones" else db.comunidad_comentarios
    doc = await collection.find_one({"_id": object_id(contenido_id), "deleted_at": None}, {"estado": 1, "moderacion": 1})
    if not doc:
        raise HTTPException(404, "Contenido no encontrado")
    return {"id": contenido_id, "estado": doc["estado"], "historial": doc.get("moderacion", [])}
