"""
Auth Service — Modelo de Sesión.

Cada vez que un usuario completa el flujo de autenticación se genera
un documento ``Session`` en la colección ``sesiones`` de MongoDB.
El ``jti`` (JWT ID) se incluye también dentro del JWT para permitir
la revocación individual de tokens sin cambiar el secreto.

Capas:
  - ``Session``         → documento MongoDB.
  - ``SessionResponse`` → respuesta pública al cliente tras login exitoso.
  - ``SessionInfo``     → info de sesión para listar sesiones activas.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Modelo interno (base de datos)
# ---------------------------------------------------------------------------

class Session(BaseModel):
    """Documento MongoDB que representa una sesión activa."""

    id: Optional[str] = Field(default=None, alias="_id")

    # Referencia al usuario propietario de la sesión
    user_id: str

    # JWT ID único — incluido como claim ``jti`` en el token
    jti: str

    # Información de contexto del dispositivo
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    dispositivo: str = "web"   # 'web' | 'mobile' | etc.

    # Tiempos
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    # Estado
    activa: bool = True
    revoked_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SessionTokenResponse(BaseModel):
    """Datos del token devueltos al cliente tras completar el login."""

    token: str
    expires_at: str = Field(..., alias="expiresAt")

    model_config = {"populate_by_name": True}


class SessionResponse(BaseModel):
    """Respuesta completa al finalizar el flujo de autenticación."""

    message: str
    token: str
    expires_at: str = Field(..., alias="expiresAt")

    model_config = {"populate_by_name": True}


class SessionInfo(BaseModel):
    """Info de una sesión individual para listar las sesiones activas del usuario."""

    id: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    dispositivo: str
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    ultima_actividad: Optional[str] = Field(default=None, alias="ultimaActividad")

    model_config = {"populate_by_name": True}


class RevokeSessionRequest(BaseModel):
    """Request para revocar una sesión específica por su ID."""

    session_id: str = Field(..., alias="sessionId")

    model_config = {"populate_by_name": True}
