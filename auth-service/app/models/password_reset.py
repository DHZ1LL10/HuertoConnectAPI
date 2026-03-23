"""
Auth Service — Modelo de Password Reset.

Cuando el usuario completa el challenge OTP de tipo ``reset-password``
se genera un ``PasswordReset`` de un solo uso con expiración de 10 minutos.
El ``token`` en texto plano se envía al cliente; solo su hash se almacena
en MongoDB (colección ``password_resets``).

Capas:
  - ``PasswordReset``       → documento MongoDB.
  - ``ResetPasswordRequest``→ request del cliente para cambiar la contraseña.
  - ``ResetPasswordResponse``→ respuesta de confirmación.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PASSWORD_RESET_EXPIRE_MINUTES: int = 10


# ---------------------------------------------------------------------------
# Modelo interno (base de datos)
# ---------------------------------------------------------------------------

class PasswordReset(BaseModel):
    """
    Documento MongoDB para un token de restablecimiento de contraseña.

    Solo se almacena el hash del token; el token en texto plano se
    entrega al cliente una única vez tras verificar el OTP.
    """

    id: Optional[str] = Field(default=None, alias="_id")

    # Hash del token de un solo uso (SHA-256 o similar)
    token_hash: str

    # Referencia al usuario que solicitó el reset
    user_id: str

    # El token expira 10 minutos después de su creación
    expires_at: datetime

    # Marca temporal de uso — None = aún no utilizado
    used_at: Optional[datetime] = None

    # Referencia al challenge OTP que originó este reset (trazabilidad)
    source_challenge_id: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True}

    @property
    def used(self) -> bool:
        """True si el token ya fue utilizado."""
        return self.used_at is not None

    @property
    def is_expired(self) -> bool:
        """True si el token ha superado su tiempo de expiración."""
        return datetime.now(timezone.utc) > self.expires_at


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    """Paso 1: el usuario indica su email para iniciar la recuperación."""

    email: str = Field(..., description="Correo electrónico de la cuenta")


class ResetPasswordRequest(BaseModel):
    """Paso 3: el usuario envía el token de reset y su nueva contraseña."""

    # Acepta ambos nombres para compatibilidad con el contrato existente
    reset_token: Optional[str] = Field(default=None, alias="resetToken")
    token: Optional[str] = None

    new_password: str = Field(
        ...,
        alias="newPassword",
        min_length=6,
        max_length=128,
        description="Nueva contraseña (mínimo 6 caracteres)",
    )

    model_config = {"populate_by_name": True}

    def get_token(self) -> Optional[str]:
        """Devuelve el token sin importar cuál campo se usó."""
        return self.reset_token or self.token


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ResetTokenResponse(BaseModel):
    """
    Respuesta tras verificar el OTP de tipo reset-password.
    Entrega el token en texto plano únicamente en este momento.
    """

    message: str
    reset_token: str = Field(..., alias="resetToken")

    model_config = {"populate_by_name": True}


class ResetPasswordResponse(BaseModel):
    """Confirmación de que la contraseña fue actualizada."""

    message: str
