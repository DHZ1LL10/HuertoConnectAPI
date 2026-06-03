"""
Auth Service — Utilidades de seguridad.

Provee hashing de contraseñas (passlib/bcrypt),
creación y decodificación de JWT (python-jose).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------------------
# Contexto de hashing — bcrypt con factor de coste por defecto (12)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Devuelve el hash bcrypt de la contraseña en texto plano."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica si *plain* coincide con el hash almacenado."""
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        # Hash might be from a different scheme (e.g. scrypt from old shared module)
        return False


# ---------------------------------------------------------------------------
# JSON Web Tokens
# ---------------------------------------------------------------------------

def create_access_token(data: dict[str, Any]) -> str:
    """
    Crea un JWT firmado con HS256.

    Args:
        data: Payload a incluir en el token. No debe contener la clave ``exp``;
              se calcula automáticamente a partir de ``JWT_EXPIRE_HOURS``.

    Returns:
        Token JWT codificado como string.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload["exp"] = expire
    payload["iat"] = datetime.now(timezone.utc)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decodifica y valida un JWT.

    Args:
        token: Token JWT en formato compacto.

    Returns:
        Payload decodificado como diccionario.

    Raises:
        jose.JWTError: Si el token es inválido, está expirado o la firma
                       no coincide.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
