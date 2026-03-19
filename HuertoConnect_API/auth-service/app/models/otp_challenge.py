"""
Auth Service — Modelo OTP Challenge.

Un ``OtpChallenge`` representa un proceso de verificación en curso
(registro, login 2FA, o reset de contraseña). Se almacena en la
colección ``otp_challenges`` de MongoDB y se elimina una vez completado.

Capas:
  - ``OtpChallenge``       → documento MongoDB.
  - ``OtpChallengeCreate`` → schema de creación interna (no expuesto al cliente).
  - ``ChallengeResponse``  → respuesta pública al iniciar el challenge.
  - ``VerifyOtpRequest``   → request del cliente para verificar el código.
  - ``ResendOtpRequest``   → request para reenviar el OTP.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

OTP_MAX_VERIFY_ATTEMPTS: int = 5
OTP_MAX_RESENDS: int = 3


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChallengeTipo(str, Enum):
    login = "login"
    registro = "registro"
    reset_password = "reset-password"


# ---------------------------------------------------------------------------
# Modelo interno (base de datos)
# ---------------------------------------------------------------------------

class OtpChallenge(BaseModel):
    """Documento MongoDB que representa un desafío OTP activo."""

    id: Optional[str] = Field(default=None, alias="_id")
    tipo: ChallengeTipo

    # Para challenges de login y reset-password; None en registro
    user_id: Optional[str] = None

    # Dirección de correo a la que se envió el OTP
    email: str

    # Datos del usuario pendiente de creación (solo en tipo=registro)
    pending_user_data: Optional[dict[str, Any]] = None

    # Hash del código OTP (nunca se almacena el código en claro)
    otp_hash: str

    # Control de intentos
    verify_attempts: int = Field(default=0, ge=0, le=OTP_MAX_VERIFY_ATTEMPTS)
    resend_count: int = Field(default=0, ge=0, le=OTP_MAX_RESENDS)

    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


# ---------------------------------------------------------------------------
# Internal creation helper (no se expone en ningún endpoint)
# ---------------------------------------------------------------------------

class OtpChallengeCreate(BaseModel):
    """DTO para crear un challenge internamente desde el service layer."""

    tipo: ChallengeTipo
    email: str
    otp_hash: str
    expires_at: datetime
    user_id: Optional[str] = None
    pending_user_data: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class VerifyOtpRequest(BaseModel):
    """Payload que el cliente envía para verificar el código OTP."""

    challenge_id: str = Field(..., alias="challengeId")
    otp_code: str = Field(
        ...,
        alias="otpCode",
        pattern=r"^\d{6}$",
        description="Código OTP de 6 dígitos",
    )

    model_config = {"populate_by_name": True}


class ResendOtpRequest(BaseModel):
    """Payload para solicitar el reenvío del OTP."""

    challenge_id: str = Field(..., alias="challengeId")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ChallengeResponse(BaseModel):
    """Respuesta devuelta al cliente al iniciar o reenviar un challenge."""

    message: str
    challenge_id: str = Field(..., alias="challengeId")
    expires_at: str = Field(..., alias="expiresAt")
    masked_email: Optional[str] = Field(default=None, alias="maskedEmail")

    # Solo expuesto en entorno de desarrollo (OTP_EXPOSE_CODE_IN_RESPONSE=true)
    dev_otp_code: Optional[str] = Field(default=None, alias="devOtpCode")

    model_config = {"populate_by_name": True}
