"""
Huertos Service — Contacto, Notificaciones, Dataset Imágenes, Usuarios Admin routes.
"""

from datetime import datetime, timezone
import os

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from app.models.schemas import (
    ContactoCreate,
    ContactoResponse,
    DatasetImagenCreate,
    DatasetImagenResponse,
    MessageResponse,
    NotificacionResponse,
    UsuarioAdminResponse,
    UsuarioAdminUpdate,
)
from shared.auth.dependencies import get_current_user, require_roles

# ===================== CONTACTO (Público) =====================

contacto_router = APIRouter(prefix="/api/public", tags=["Público"])


@contacto_router.post("/contacto", response_model=ContactoResponse, status_code=201)
async def create_contacto(body: ContactoCreate, request: Request):
    """Public contact form — no auth required."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    doc = {
        "nombre": body.nombre,
        "email": body.email,
        "telefono": body.telefono,
        "mensaje": body.mensaje,
        "leido": False,
        "fecha": now,
    }
    result = await db.contacto_mensajes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ContactoResponse(
        id=str(doc["_id"]),
        nombre=doc["nombre"],
        email=doc["email"],
        telefono=doc["telefono"],
        mensaje=doc["mensaje"],
        leido=False,
        fecha=now.isoformat(),
    )


@contacto_router.get("/contacto", response_model=list[ContactoResponse])
async def list_contactos(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """List contact messages — Admin only."""
    db = request.app.state.mongodb
    cursor = db.contacto_mensajes.find().sort("fecha", -1).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    return [
        ContactoResponse(
            id=str(c["_id"]),
            nombre=c["nombre"],
            email=c["email"],
            telefono=c.get("telefono", ""),
            mensaje=c["mensaje"],
            leido=c.get("leido", False),
            fecha=c.get("fecha", "").isoformat() if c.get("fecha") else None,
        )
        for c in items
    ]


# ===================== USUARIOS (Admin) =====================

usuarios_router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"])


@usuarios_router.get("", response_model=list[UsuarioAdminResponse])
async def list_usuarios(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    rol: str | None = None,
    estado: str | None = None,
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """List all users — Admin only."""
    db = request.app.state.mongodb
    query: dict = {"deleted_at": None}
    if rol:
        query["rol"] = rol
    if estado:
        query["estado"] = estado

    cursor = db.usuarios.find(query).skip(skip).limit(limit)
    users = await cursor.to_list(limit)
    return [
        UsuarioAdminResponse(
            id=str(u["_id"]),
            nombre=u["nombre"],
            apellidos=u.get("apellidos", ""),
            email=u["email"],
            rol=u["rol"],
            estado=u["estado"],
            email_verificado=u.get("email_verificado", False),
            region_id=str(u["region_id"]) if u.get("region_id") else None,
            ultima_actividad=u.get("ultima_actividad", "").isoformat() if u.get("ultima_actividad") else None,
            created_at=u.get("created_at", "").isoformat() if u.get("created_at") else None,
        )
        for u in users
    ]


@usuarios_router.get("/{user_id}", response_model=UsuarioAdminResponse)
async def get_usuario(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get user profile — own profile or Admin."""
    db = request.app.state.mongodb

    if current_user["rol"] != "Admin" and current_user["id"] != user_id:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    u = await db.usuarios.find_one({"_id": ObjectId(user_id), "deleted_at": None})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return UsuarioAdminResponse(
        id=str(u["_id"]),
        nombre=u["nombre"],
        apellidos=u.get("apellidos", ""),
        email=u["email"],
        rol=u["rol"],
        estado=u["estado"],
        email_verificado=u.get("email_verificado", False),
        region_id=str(u["region_id"]) if u.get("region_id") else None,
        ultima_actividad=u.get("ultima_actividad", "").isoformat() if u.get("ultima_actividad") else None,
        created_at=u.get("created_at", "").isoformat() if u.get("created_at") else None,
    )


@usuarios_router.patch("/{user_id}", response_model=UsuarioAdminResponse)
async def update_usuario(
    user_id: str,
    body: UsuarioAdminUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update user — Admin can update any, users can update own profile (limited)."""
    db = request.app.state.mongodb

    # Regular users can only update their own basic info
    if current_user["rol"] != "Admin":
        if current_user["id"] != user_id:
            raise HTTPException(status_code=403, detail="Acceso denegado")
        # Non-admin can't change rol or estado
        if body.rol or body.estado:
            raise HTTPException(status_code=403, detail="No puede cambiar rol o estado")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No data to update")

    update_data["updated_at"] = datetime.now(timezone.utc)
    result = await db.usuarios.update_one({"_id": ObjectId(user_id), "deleted_at": None}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u = await db.usuarios.find_one({"_id": ObjectId(user_id)})
    return UsuarioAdminResponse(
        id=str(u["_id"]),
        nombre=u["nombre"],
        apellidos=u.get("apellidos", ""),
        email=u["email"],
        rol=u["rol"],
        estado=u["estado"],
        email_verificado=u.get("email_verificado", False),
        region_id=str(u["region_id"]) if u.get("region_id") else None,
        ultima_actividad=u.get("ultima_actividad", "").isoformat() if u.get("ultima_actividad") else None,
        created_at=u.get("created_at", "").isoformat() if u.get("created_at") else None,
    )


@usuarios_router.delete("/{user_id}", response_model=MessageResponse)
async def delete_usuario(
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin"])),
):
    """Soft-delete user — Admin only."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    result = await db.usuarios.update_one(
        {"_id": ObjectId(user_id), "deleted_at": None},
        {"$set": {"deleted_at": now, "estado": "Inactivo", "updated_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return MessageResponse(message="Usuario eliminado")


@usuarios_router.patch("/{user_id}/foto", response_model=UsuarioAdminResponse)
async def update_foto_perfil(
    user_id: str,
    request: Request,
    foto: UploadFile = File(..., description="Imagen de perfil (JPG/PNG/WebP, máx 5 MB)"),
    current_user: dict = Depends(get_current_user),
):
    """
    Sube una imagen de perfil a Cloudinary y actualiza ``profile_picture``.

    - El usuario sólo puede actualizar su propia foto.
    - Admin puede actualizar la foto de cualquier usuario.
    - Formatos permitidos: JPG, PNG, WebP (máx 5 MB).
    """
    # Control de acceso: propio perfil o Admin
    caller_role = (current_user.get("rol") or current_user.get("role") or "").lower()
    caller_id = str(current_user.get("id") or current_user.get("_id") or "")
    if caller_role != "admin" and caller_id != user_id:
        raise HTTPException(status_code=403, detail="Solo puedes actualizar tu propio perfil.")

    # Validación del archivo
    ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_EXT  = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_BYTES    = 5 * 1024 * 1024  # 5 MB

    filename = foto.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    content_type = foto.content_type or ""

    if ext not in ALLOWED_EXT or content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato no permitido '{ext}'. Usa JPG, PNG o WebP.",
        )

    file_bytes = await foto.read()
    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera el límite de 5 MB.",
        )

    # Verificar que el usuario existe
    db = request.app.state.mongodb
    u = await db.usuarios.find_one({"_id": ObjectId(user_id), "deleted_at": None})
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Subir a Cloudinary
    try:
        from shared.services.cloudinary_service import upload_image, delete_image

        # Eliminar foto anterior si tiene public_id guardado
        old_pid = u.get("profile_picture_public_id")
        if old_pid:
            await delete_image(old_pid)

        cloud_result = await upload_image(
            file_bytes,
            folder="huerto-connect/perfiles",
            public_id=f"usuario_{user_id}",
        )
        secure_url = cloud_result["secure_url"]
        public_id  = cloud_result["public_id"]

    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Actualizar en MongoDB
    now = datetime.now(timezone.utc)
    await db.usuarios.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "profile_picture": secure_url,
            "profile_picture_public_id": public_id,
            "updated_at": now,
        }},
    )

    u = await db.usuarios.find_one({"_id": ObjectId(user_id)})
    return UsuarioAdminResponse(
        id=str(u["_id"]),
        nombre=u["nombre"],
        apellidos=u.get("apellidos", ""),
        email=u["email"],
        rol=u["rol"],
        estado=u["estado"],
        email_verificado=u.get("email_verificado", False),
        region_id=str(u["region_id"]) if u.get("region_id") else None,
        ultima_actividad=u.get("ultima_actividad", "").isoformat() if u.get("ultima_actividad") else None,
        created_at=u.get("created_at", "").isoformat() if u.get("created_at") else None,
    )



notificaciones_router = APIRouter(prefix="/api/notificaciones", tags=["Notificaciones"])


@notificaciones_router.get("", response_model=list[NotificacionResponse])
async def list_notificaciones(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """List notifications for current user."""
    db = request.app.state.mongodb
    cursor = db.notificaciones_usuario.find(
        {"usuario_id": current_user["id"]}
    ).sort("fecha", -1).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    return [
        NotificacionResponse(
            id=str(n["_id"]),
            usuario_id=n["usuario_id"],
            titulo=n["titulo"],
            mensaje=n["mensaje"],
            tipo=n.get("tipo", "info"),
            leida=n.get("leida", False),
            referencia_id=n.get("referencia_id"),
            referencia_tipo=n.get("referencia_tipo"),
            fecha=n.get("fecha", "").isoformat() if n.get("fecha") else None,
        )
        for n in items
    ]


@notificaciones_router.patch("/{notif_id}/leer", response_model=MessageResponse)
async def mark_notification_read(
    notif_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Mark a notification as read."""
    db = request.app.state.mongodb
    result = await db.notificaciones_usuario.update_one(
        {"_id": ObjectId(notif_id), "usuario_id": current_user["id"]},
        {"$set": {"leida": True}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    return MessageResponse(message="Notificación marcada como leída")


# ===================== DATASET IMAGENES =====================

dataset_router = APIRouter(prefix="/api/datasets/imagenes", tags=["Dataset Imágenes"])


@dataset_router.post("", response_model=DatasetImagenResponse, status_code=201)
async def upload_dataset_image(
    body: DatasetImagenCreate,
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Upload an image to the training dataset."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    doc = {
        "imagen_url": body.imagen_url,
        "huerto_id": body.huerto_id,
        "cultivo_id": body.cultivo_id,
        "etiqueta_plaga": body.etiqueta_plaga,
        "etiqueta_severidad": body.etiqueta_severidad,
        "anotaciones_json": body.anotaciones_json,
        "fuente": body.fuente,
        "validada": body.validada,
        "fecha_captura": now,
    }
    result = await db.dataset_imagenes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return DatasetImagenResponse(
        id=str(doc["_id"]),
        imagen_url=doc["imagen_url"],
        huerto_id=doc.get("huerto_id"),
        cultivo_id=doc.get("cultivo_id"),
        etiqueta_plaga=doc.get("etiqueta_plaga"),
        etiqueta_severidad=doc.get("etiqueta_severidad"),
        fuente=doc["fuente"],
        validada=doc["validada"],
        fecha_captura=now.isoformat(),
    )


@dataset_router.get("", response_model=list[DatasetImagenResponse])
async def list_dataset_images(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    validada: bool | None = None,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """List dataset images with optional filtering."""
    db = request.app.state.mongodb
    query = {}
    if validada is not None:
        query["validada"] = validada

    cursor = db.dataset_imagenes.find(query).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    return [
        DatasetImagenResponse(
            id=str(d["_id"]),
            imagen_url=d["imagen_url"],
            huerto_id=d.get("huerto_id"),
            cultivo_id=d.get("cultivo_id"),
            etiqueta_plaga=d.get("etiqueta_plaga"),
            etiqueta_severidad=d.get("etiqueta_severidad"),
            fuente=d.get("fuente", "manual"),
            validada=d.get("validada", False),
            fecha_captura=d.get("fecha_captura", "").isoformat() if d.get("fecha_captura") else None,
        )
        for d in items
    ]
