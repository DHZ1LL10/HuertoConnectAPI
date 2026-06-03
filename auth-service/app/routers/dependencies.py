"""
Auth Service — Dependencia de autenticación JWT + sesión activa.

Provee:
  - ``bearer_scheme``    → extrae el Bearer token del header Authorization.
  - ``get_current_user`` → decodifica el JWT y valida que la sesión esté
                           activa en MongoDB. Úsalo con ``Depends(get_current_user)``.

Uso en un endpoint:

    from app.routers.dependencies import get_current_user

    @router.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return user
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.database import get_db
from app.core.security import decode_token

# Swagger/OpenAPI: usa auth Bearer directa (más compatible con flujo OTP)
bearer_scheme = HTTPBearer(auto_error=False)


async def _extract_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """
    Extrae el token Bearer desde el esquema HTTP de Swagger o desde headers.
    """
    if credentials and credentials.credentials:
        return credentials.credentials

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticación requerido.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(token: str = Depends(_extract_bearer_token)) -> dict:
    """
    Dependencia FastAPI que autentica al usuario a partir del JWT Bearer.

    Flujo:
    1. Decodifica y valida el JWT (firma + expiración).
    2. Extrae ``sub`` (user_id) y ``jti`` (JWT ID) del payload.
    3. Consulta la colección ``sesiones`` para verificar que la sesión
       está activa y no ha sido revocada.
    4. Carga el documento del usuario desde ``usuarios``.

    Returns:
        Documento del usuario (dict) con ``_id`` como ObjectId.

    Raises:
        HTTPException 401: token inválido, expirado, jti no encontrado
                           o sesión revocada.
        HTTPException 403: cuenta inactiva o eliminada.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exc

    user_id: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")

    if not user_id or not jti:
        raise credentials_exc

    db = get_db()

    # Verificar sesión activa en MongoDB
    from bson import ObjectId

    session = await db.sesiones.find_one({"jti": jti, "activa": True})
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida o revocada. Inicia sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Cargar usuario
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise credentials_exc

    user = await db.usuarios.find_one({"_id": oid, "deleted_at": None})
    if not user:
        raise credentials_exc

    if user.get("estado") != "Activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva o suspendida.",
        )

    # Añadir el jti al user dict para que los endpoints de sesiones puedan
    # identificar la sesión actual sin necesidad de re-parsear el token.
    user["_current_jti"] = jti
    return user
