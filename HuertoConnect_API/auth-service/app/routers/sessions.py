"""
Auth Service — Router de sesiones.

Endpoints:
  GET    /auth/session             → valida JWT, retorna datos del usuario actual
  POST   /auth/logout              → revoca la sesión actual
  GET    /auth/sesiones            → lista sesiones activas del usuario
  DELETE /auth/sesiones/{id}       → revoca una sesión específica
  POST   /auth/sesiones/revoke-all → revoca todas las sesiones excepto la actual
"""

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.routers.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Sesiones"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: str
    nombre: str
    apellidos: str
    email: str
    role: str
    estado: str
    email_verificado: bool
    profile_picture: str | None = None
    auth_provider: str


class SessionInfoOut(BaseModel):
    id: str
    ip: str | None = None
    user_agent: str | None = None
    dispositivo: str
    created_at: str | None = Field(default=None, alias="createdAt")
    ultima_actividad: str | None = Field(default=None, alias="ultimaActividad")
    is_current: bool = Field(default=False, alias="isCurrent")

    model_config = {"populate_by_name": True}


class MessageOut(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# GET /auth/session
# ---------------------------------------------------------------------------

@router.get(
    "/session",
    response_model=UserOut,
    summary="Valida el JWT y retorna datos del usuario",
)
async def get_session(current_user: dict = Depends(get_current_user)):
    """
    Verifica que el token JWT sea válido y la sesión esté activa.
    Devuelve los datos públicos del usuario autenticado.
    """
    return UserOut(
        id=str(current_user["_id"]),
        nombre=current_user.get("nombre", ""),
        apellidos=current_user.get("apellidos", ""),
        email=current_user["email"],
        role=current_user.get("role", "usuario"),
        estado=current_user.get("estado", "Activo"),
        email_verificado=current_user.get("email_verificado", False),
        profile_picture=current_user.get("profile_picture"),
        auth_provider=current_user.get("auth_provider", "email"),
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    response_model=MessageOut,
    summary="Cierra la sesión actual",
)
async def logout(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Revoca la sesión activa identificada por el ``jti`` del JWT actual.
    """
    db = get_db()
    jti = current_user.get("_current_jti")

    await db.sesiones.update_one(
        {"jti": jti},
        {"$set": {
            "activa": False,
            "revoked_at": datetime.now(timezone.utc),
        }},
    )
    return MessageOut(message="Sesión cerrada correctamente.")


# ---------------------------------------------------------------------------
# GET /auth/sesiones
# ---------------------------------------------------------------------------

@router.get(
    "/sesiones",
    response_model=list[SessionInfoOut],
    summary="Lista todas las sesiones activas del usuario",
)
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """
    Retorna todas las sesiones activas del usuario autenticado.
    La sesión actual se marca con ``isCurrent: true``.
    """
    db = get_db()
    user_id = str(current_user["_id"])
    current_jti = current_user.get("_current_jti")

    cursor = db.sesiones.find(
        {"user_id": user_id, "activa": True}
    ).sort("created_at", -1).limit(50)

    sessions = await cursor.to_list(50)

    return [
        SessionInfoOut(
            id=str(s["_id"]),
            ip=s.get("ip"),
            user_agent=s.get("user_agent"),
            dispositivo=s.get("dispositivo", "web"),
            createdAt=s["created_at"].isoformat() if s.get("created_at") else None,
            ultimaActividad=s.get("ultima_actividad", s.get("created_at", "")).isoformat()
                if s.get("ultima_actividad") or s.get("created_at") else None,
            isCurrent=(s.get("jti") == current_jti),
        )
        for s in sessions
    ]


# ---------------------------------------------------------------------------
# DELETE /auth/sesiones/{session_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/sesiones/{session_id}",
    response_model=MessageOut,
    summary="Revoca una sesión específica",
)
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Marca como inactiva la sesión con el ``session_id`` indicado.
    Solo el propietario de la sesión puede revocarla.
    """
    db = get_db()
    user_id = str(current_user["_id"])

    try:
        oid = ObjectId(session_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de sesión inválido.",
        )

    result = await db.sesiones.update_one(
        {"_id": oid, "user_id": user_id, "activa": True},
        {"$set": {
            "activa": False,
            "revoked_at": datetime.now(timezone.utc),
        }},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sesión no encontrada o ya fue cerrada.",
        )

    return MessageOut(message="Sesión cerrada.")


# ---------------------------------------------------------------------------
# POST /auth/sesiones/revoke-all
# ---------------------------------------------------------------------------

@router.post(
    "/sesiones/revoke-all",
    response_model=MessageOut,
    summary="Cierra todas las sesiones excepto la actual",
)
async def revoke_all_sessions(current_user: dict = Depends(get_current_user)):
    """
    Revoca todas las sesiones activas del usuario **excepto** la sesión
    a través de la cual se realizó esta petición.
    """
    db = get_db()
    user_id = str(current_user["_id"])
    current_jti = current_user.get("_current_jti")
    now = datetime.now(timezone.utc)

    result = await db.sesiones.update_many(
        {
            "user_id": user_id,
            "activa": True,
            "jti": {"$ne": current_jti},  # excluir sesión actual
        },
        {"$set": {"activa": False, "revoked_at": now}},
    )

    count = result.modified_count
    return MessageOut(
        message=f"Se cerraron {count} sesión(es) activa(s) en otros dispositivos."
    )
