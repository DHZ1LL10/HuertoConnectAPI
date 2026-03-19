"""
Huerto Connect — Auth Dependencies
FastAPI dependency injection for authentication and RBAC.
"""

from functools import wraps
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from shared.auth.security import decode_jwt_token, hash_token
from shared.config import settings

# This makes Swagger UI show the "Authorize" button with Bearer token input
bearer_scheme = HTTPBearer(auto_error=False)


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

    session = await db.sesiones.find_one({
        "token_hash": token_hashed,
        "activa": True,
    })
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión no encontrada o revocada",
        )

    # Get user info
    from bson import ObjectId
    user = await db.usuarios.find_one({
        "_id": ObjectId(payload["sub"]),
        "deleted_at": None,
    })
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if user.get("estado") != "Activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta de usuario inactiva o suspendida",
        )

    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "nombre": user["nombre"],
        "apellidos": user.get("apellidos", ""),
        "rol": user["rol"],
        "estado": user["estado"],
        "region_id": user.get("region_id"),
    }


def require_roles(allowed_roles: list[str]):
    """
    Dependency factory for RBAC.
    Usage: Depends(require_roles(["Admin", "Tecnico"]))
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["rol"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Roles permitidos: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker
