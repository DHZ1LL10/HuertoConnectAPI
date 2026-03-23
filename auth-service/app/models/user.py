"""
Auth Service — Modelo de Usuario.

Separa claramente tres capas:
  - ``UserInDB``     → representación interna (MongoDB document), incluye password_hash.
  - ``UserCreate``   → schema de request para registro manual.
  - ``UserResponse`` → schema de respuesta pública (sin datos sensibles).
  - ``UserUpdate``   → schema de request para actualización parcial (PATCH).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    admin = "admin"
    tecnico = "tecnico"
    usuario = "usuario"


class AuthProvider(str, Enum):
    email = "email"
    google = "google"


class UserEstado(str, Enum):
    activo = "Activo"
    inactivo = "Inactivo"
    suspendido = "Suspendido"


# ---------------------------------------------------------------------------
# Modelo interno (base de datos)
# ---------------------------------------------------------------------------

class UserInDB(BaseModel):
    """Representación del documento de usuario almacenado en MongoDB."""

    id: Optional[str] = Field(default=None, alias="_id")
    nombre: str
    apellidos: str = ""
    email: EmailStr
    password_hash: Optional[str] = None          # None cuando auth_provider=google
    role: UserRole = UserRole.usuario
    google_id: Optional[str] = None
    profile_picture: Optional[str] = None
    auth_provider: AuthProvider = AuthProvider.email
    estado: UserEstado = UserEstado.activo
    email_verificado: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,   # acepta tanto 'id' como '_id'
        "use_enum_values": True,
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Datos que el cliente envía para crear una cuenta por email."""

    nombre: str = Field(..., min_length=1, max_length=100)
    apellidos: str = Field(default="", max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    confirm_password: str = Field(..., min_length=6, max_length=128)

    def passwords_match(self) -> bool:
        return self.password == self.confirm_password


class UserUpdate(BaseModel):
    """Actualización parcial del perfil (campos opcionales)."""

    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    apellidos: Optional[str] = Field(default=None, max_length=100)
    profile_picture: Optional[str] = None
    # Campos exclusivos de Admin
    role: Optional[UserRole] = None
    estado: Optional[UserEstado] = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Datos del usuario devueltos al cliente (sin información sensible)."""

    id: str
    nombre: str
    apellidos: str
    email: str
    role: UserRole
    profile_picture: Optional[str] = None
    auth_provider: AuthProvider
    estado: UserEstado
    email_verificado: bool
    created_at: datetime

    model_config = {"use_enum_values": True}
