"""
Huerto Connect — Auth Dependencies
FastAPI dependency injection for authentication and RBAC.
"""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from shared.auth.security import decode_jwt_token, hash_token

# This makes Swagger UI show the "Authorize" button with Bearer token input
bearer_scheme = HTTPBearer(auto_error=False)


def _normalize_role(value: str | None) -> str:
    """Normalize role names across legacy docs (role) and current docs (rol)."""
    if not value:
        return "Usuario"
    lowered = str(value).strip().lower()
    mapping = {
        "admin": "Admin",
        "tecnico": "Tecnico",
        "usuario": "Usuario",
    }
    return mapping.get(lowered, str(value).strip())


def _normalize_user_id(raw: object | None) -> str | None:
    """Convert user ids from ObjectId/string into a comparable string."""
    if raw is None:
        return None
    return str(raw).strip()


async def get_token_from_header(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """Extract Bearer token from Authorization header (with Swagger UI support)."""
    if credentials and credentials.credentials:
        return credentials.credentials

    # Fallback: manual extraction (for proxied requests, etc.)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
        )
    return auth_header[7:]


async def get_current_user(
    request: Request,
    token: str = Depends(get_token_from_header),
) -> dict:
    """
    Dependency to get the current authenticated user.
    Validates JWT token and checks session in MongoDB.
    """

    # Decode JWT
    payload = decode_jwt_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
        )

    # Verify session exists and is active in MongoDB
    db: AsyncIOMotorDatabase = request.app.state.mongodb
    token_hashed = hash_token(token)
    now = datetime.now(timezone.utc)
    jwt_user_id = _normalize_user_id(payload.get("sub"))
    jwt_jti = payload.get("jti")

    if not jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: falta 'sub'",
        )

    # Legacy/session-token flow used by huertos/plagas/reportes services.
    session = await db.sesiones.find_one(
        {
        "token_hash": token_hashed,
        "activa": True,
        "$or": [
            {"expires_at": {"$exists": False}},
            {"expires_at": None},
            {"expires_at": {"$gt": now}},
        ],
    }
    )

    # Auth-service flow stores sessions by jti + user_id.
    if not session and jwt_jti:
        session = await db.sesiones.find_one(
            {
                "jti": jwt_jti,
                "activa": True,
                "$or": [
                    {"expires_at": {"$exists": False}},
                    {"expires_at": None},
                    {"expires_at": {"$gt": now}},
                ],
            }
        )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no encontrada o revocada",
        )

    # Ensure the located session belongs to the same user as JWT sub.
    session_user_id = _normalize_user_id(session.get("usuario_id") or session.get("user_id"))
    if session_user_id and session_user_id != jwt_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida para el usuario autenticado",
        )

    # Get user info
    try:
        user_oid = ObjectId(jwt_user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido: usuario no válido",
        )

    user = await db.usuarios.find_one({"_id": user_oid, "deleted_at": None})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    user_estado = str(user.get("estado", "Activo"))
    if user_estado.lower() != "activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta de usuario inactiva o suspendida",
        )

    normalized_role = _normalize_role(
        user.get("rol") or user.get("role") or payload.get("rol") or payload.get("role")
    )

    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "nombre": user.get("nombre", ""),
        "apellidos": user.get("apellidos", ""),
        "rol": normalized_role,
        "role": normalized_role,
        "estado": user_estado,
        "region_id": user.get("region_id"),
    }


def require_roles(allowed_roles: list[str]):
    """
    Dependency factory for RBAC.
    Usage: Depends(require_roles(["Admin", "Tecnico"]))
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        current_role = _normalize_role(current_user.get("rol"))
        normalized_allowed = {_normalize_role(r) for r in allowed_roles}
        if current_role not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles permitidos: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker
