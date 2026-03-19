"""
Auth Service — Google OAuth2 ID Token verification.

Verifica tokens de Google Sign-In usando la librería oficial ``google-auth``.
No hace solicitudes externas más allá de la validación del token JWT
firmado por Google (usa las claves públicas de Google con caché automático).
"""

import httpx
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from fastapi import HTTPException, status

from app.core.config import settings


# ---------------------------------------------------------------------------
# Transport singleton (reutiliza la sesión HTTP)
# ---------------------------------------------------------------------------

_transport = google_requests.Request()


# ---------------------------------------------------------------------------
# Verificación del token
# ---------------------------------------------------------------------------

async def verify_google_token(credential: str) -> dict:
    """
    Verifica un Google ID token y devuelve el payload.

    Args:
        credential: Token JWT emitido por Google Sign-In (``credential``
                    de la respuesta de ``google.accounts.id.initialize``).

    Returns:
        Diccionario con los claims del token. Los campos más relevantes son:
        - ``sub``     → Google user ID único
        - ``email``   → correo electrónico verificado
        - ``name``    → nombre completo
        - ``given_name`` / ``family_name``
        - ``picture`` → URL de la foto de perfil

    Raises:
        HTTPException 401: Si el token es inválido, expirado, o no corresponde
                           al ``GOOGLE_CLIENT_ID`` configurado.
        HTTPException 400: Si el token no contiene email verificado.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sign-In no está configurado en este entorno.",
        )

    try:
        payload = id_token.verify_oauth2_token(
            credential,
            _transport,
            audience=settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token de Google inválido o expirado: {exc}",
        )

    # Validar que el email esté verificado por Google
    if not payload.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo de la cuenta de Google no está verificado.",
        )

    return payload


def extract_google_user_info(payload: dict) -> dict:
    """
    Extrae los campos de usuario del payload del token de Google.

    Returns:
        Diccionario con: ``google_id``, ``email``, ``nombre``,
        ``apellidos``, ``picture``.
    """
    full_name = payload.get("name", "")
    given = payload.get("given_name", "")
    family = payload.get("family_name", "")

    # Fallback: si no hay given/family, dividir el name
    if not given and full_name:
        parts = full_name.split(" ", 1)
        given = parts[0]
        family = parts[1] if len(parts) > 1 else ""

    return {
        "google_id": payload["sub"],
        "email": payload["email"].lower(),
        "nombre": given or full_name,
        "apellidos": family,
        "picture": payload.get("picture"),
    }
