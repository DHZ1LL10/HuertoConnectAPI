"""
Auth Service — Router de Google SSO y recuperación de contraseña.

Endpoints:
  POST /auth/google           → Login / registro con Google ID token.
  POST /auth/forgot-password  → Inicia flujo de reset: envía OTP por email.
  POST /auth/reset-password   → Cambia contraseña con token de un solo uso.

Google SSO:
  - Token verificado con google-auth (sin OTP adicional).
  - Si el usuario no existe se crea automáticamente con email_verificado=True.
  - Si existe se actualiza profile_picture y auth_provider.
  - Genera sesión + JWT directamente.

Forgot / Reset password:
  - forgot-password: anti-enumeración (responde 200 aunque el email no exista).
  - reset-password: token de 10 min, uso único (marked used_at).
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models import (
    AuthProvider,
    ChallengeTipo,
    OtpChallengeCreate,
    UserEstado,
    UserRole,
)
from app.services import google_service, otp_service
from app.services.mail_adapter import send_otp_background
from app.services.mail_service import mask_email

router = APIRouter(prefix="/auth", tags=["Auth Google & Password"])

_RESET_EXPIRE_MINUTES = 10
_RESET_COLLECTION = "password_resets"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_token(raw: str) -> str:
    """SHA-256 del token de reset (nunca se almacena en claro)."""
    return hashlib.sha256(raw.encode()).hexdigest()


async def _open_session(db, user_id: str, request: Request) -> tuple[str, str]:
    """
    Crea sesión en MongoDB y devuelve (jwt_token, expires_iso).
    Reutiliza la misma lógica que auth_otp._create_session.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    token = create_access_token({"sub": user_id, "jti": jti})

    await db.sesiones.insert_one({
        "user_id": user_id,
        "jti": jti,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "dispositivo": request.headers.get("x-device", "web"),
        "created_at": now,
        "expires_at": expires_at,
        "activa": True,
        "revoked_at": None,
    })
    return token, expires_at.isoformat()


# ---------------------------------------------------------------------------
# Schemas locales
# ---------------------------------------------------------------------------

class GoogleLoginRequest(BaseModel):
    """Payload del botón de Google Sign-In (campo ``credential``)."""
    credential: str = Field(
        ...,
        min_length=1,
        description="Google ID token (JWT) recibido desde Google Sign-In.",
        examples=["eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2OTM4In0.eyJpc3MiOiJodHRwcy4uLg.signature"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "credential": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2OTM4In0.eyJpc3MiOiJodHRwcy4uLg.signature",
            }
        }
    }


class AuthOut(BaseModel):
    message: str
    token: str
    expires_at: str = Field(..., alias="expiresAt")
    user_id: str = Field(..., alias="userId")
    is_new_user: bool = Field(default=False, alias="isNewUser")
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "message": "Inicio de sesión con Google exitoso.",
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "expiresAt": "2026-03-21T23:30:00+00:00",
                "userId": "65f2d6ea9f3d2a3e8a7b9c10",
                "isNewUser": False,
            }
        },
    }


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "ana.garcia@huertoconnect.com",
            }
        }
    }


class ForgotPasswordOut(BaseModel):
    message: str
    challenge_id: str = Field(default="", alias="challengeId")
    expires_at: str = Field(default="", alias="expiresAt")
    masked_email: str = Field(default="", alias="maskedEmail")
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "message": "Código para cambio de contraseña enviado al correo electrónico.",
                "challengeId": "65f3a2018f8f6d66ad4b8123",
                "expiresAt": "2026-03-21T20:15:00+00:00",
                "maskedEmail": "an***@huertoconnect.com",
            }
        },
    }


class ResetPasswordRequest(BaseModel):
    reset_token: str | None = Field(default=None, alias="resetToken")
    token: str | None = None
    new_password: str = Field(..., alias="newPassword", min_length=6, max_length=128)
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "resetToken": "Y3tiU2YHq8E3Qn3xY5v2xwW6o8nZ9K2hPqM1fR4sT",
                "newPassword": "NuevaPass2026!",
            }
        },
    }

    def get_token(self) -> str | None:
        return self.reset_token or self.token


class MessageOut(BaseModel):
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Contraseña actualizada exitosamente. Ya puedes iniciar sesión.",
            }
        }
    }


# ---------------------------------------------------------------------------
# POST /auth/google
# ---------------------------------------------------------------------------

@router.post(
    "/google",
    response_model=AuthOut,
    summary="Login / Registro con Google Sign-In",
)
async def google_login(
    body: GoogleLoginRequest,
    request: Request,
):
    """
    Verifica el Google ID token y abre sesión directamente (sin OTP).

    - Usuario nuevo → se crea con ``email_verificado=True``.
    - Usuario existente → se actualiza ``profile_picture`` y ``auth_provider``.
    """
    # 1. Verificar token con Google
    payload = await google_service.verify_google_token(body.credential)
    info = google_service.extract_google_user_info(payload)

    db = get_db()
    now = datetime.now(timezone.utc)
    is_new = False

    # 2. Buscar usuario por email (incluyendo soft-delete)
    user = await db.usuarios.find_one({"email": info["email"]})

    if user:
        was_soft_deleted = user.get("deleted_at") is not None

        # Cuentas inactivas/suspendidas activas (no borradas) siguen bloqueadas.
        if not was_soft_deleted and user.get("estado") != "Activo":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cuenta inactiva o suspendida.",
            )

        # Actualizar foto/proveedor y, si estaba eliminada, restaurarla.
        update_data = {
            "profile_picture": info["picture"],
            "google_id": info["google_id"],
            "auth_provider": AuthProvider.google,
            "email_verificado": True,
            "ultima_actividad": now,
            "updated_at": now,
        }
        if was_soft_deleted:
            update_data["deleted_at"] = None
            update_data["estado"] = UserEstado.activo

        await db.usuarios.update_one(
            {"_id": user["_id"]},
            {"$set": update_data},
        )
        user_id = str(user["_id"])
        is_new = was_soft_deleted

    else:
        # Crear usuario nuevo
        new_user = {
            "nombre": info["nombre"],
            "apellidos": info["apellidos"],
            "email": info["email"],
            "password_hash": None,          # cuenta Google, sin contraseña local
            "role": UserRole.usuario,
            "auth_provider": AuthProvider.google,
            "google_id": info["google_id"],
            "profile_picture": info["picture"],
            "estado": UserEstado.activo,
            "email_verificado": True,
            "region_id": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        result = await db.usuarios.insert_one(new_user)
        user_id = str(result.inserted_id)
        is_new = True

    # 3. Crear sesión + JWT
    token, expires_iso = await _open_session(db, user_id, request)

    msg = "Registro exitoso con Google." if is_new else "Inicio de sesión con Google exitoso."
    return AuthOut(
        message=msg,
        token=token,
        expiresAt=expires_iso,
        userId=user_id,
        isNewUser=is_new,
    )


# ---------------------------------------------------------------------------
# POST /auth/forgot-password
# ---------------------------------------------------------------------------

@router.post(
    "/forgot-password",
    response_model=ForgotPasswordOut,
    summary="Inicia el flujo de recuperación de contraseña",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
):
    """
    Busca al usuario por email y envía un OTP de tipo ``reset-password``.

    Anti-enumeración: siempre responde con 200, sin revelar si el email existe.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)

    user = await db.usuarios.find_one({
        "email": body.email.lower(),
        "deleted_at": None,
    })

    # Respuesta genérica para emails no registrados (anti-enumeración)
    if not user:
        return ForgotPasswordOut(
            message="Si el correo está registrado, recibirás un código para cambiar tu contraseña.",
            challengeId="",
            expiresAt=expires_at.isoformat(),
            maskedEmail=mask_email(body.email),
        )

    otp_code = otp_service.generate_otp()
    otp_hash = otp_service.hash_otp(otp_code)

    challenge_data = OtpChallengeCreate(
        tipo=ChallengeTipo.reset_password,
        email=user["email"],
        otp_hash=otp_hash,
        expires_at=expires_at,
        user_id=str(user["_id"]),
    )
    challenge_id = await otp_service.create_challenge(db, challenge_data)

    full_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))
    await send_otp_background(
        background_tasks,
        email=user["email"],
        otp_code=otp_code,
        tipo="reset-password",
        recipient_name=full_name,
        challenge_id=challenge_id,
        expires_at=expires_at.isoformat(),
    )

    out = ForgotPasswordOut(
        message="Código para cambio de contraseña enviado al correo electrónico.",
        challengeId=challenge_id,
        expiresAt=expires_at.isoformat(),
        maskedEmail=mask_email(user["email"]),
    )
    if getattr(settings, "OTP_EXPOSE_CODE_IN_RESPONSE", False):
        out.__dict__["devOtpCode"] = otp_code

    return out


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------

@router.post(
    "/reset-password",
    response_model=MessageOut,
    summary="Cambia la contraseña usando el token de un solo uso",
)
async def reset_password(body: ResetPasswordRequest):
    """
    Valida el token de reset (10 min, un solo uso) y actualiza la contraseña.

    El token se obtiene del endpoint ``POST /auth/verify-otp`` cuando el
    challenge es de tipo ``reset-password``.

    Tras el cambio se revocan todas las sesiones activas del usuario.
    """
    raw_token = body.get_token()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requiere el token de restablecimiento.",
        )

    token_hash = _hash_token(raw_token)
    db = get_db()
    now = datetime.now(timezone.utc)

    reset_doc = await db[_RESET_COLLECTION].find_one({
        "token_hash": token_hash,
        "used_at": None,
    })

    if not reset_doc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace de restablecimiento expiró o ya fue usado. Solicita uno nuevo.",
        )

    # Verificar expiración
    expires = reset_doc["expires_at"]
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Token expirado. Solicita un nuevo enlace de recuperación.",
        )

    # Actualizar contraseña (bcrypt hash — single string)
    new_hash = hash_password(body.new_password)
    user_oid = reset_doc["user_id"] if isinstance(reset_doc["user_id"], ObjectId) \
        else ObjectId(reset_doc["user_id"])
    await db.usuarios.update_one(
        {"_id": user_oid},
        {"$set": {
            "password_hash": new_hash,
            "updated_at": now,
        }},
    )

    # Marcar token como usado
    await db[_RESET_COLLECTION].update_one(
        {"_id": reset_doc["_id"]},
        {"$set": {"used_at": now}},
    )

    # Revocar todas las sesiones activas (seguridad post-reset)
    user_id_str = str(reset_doc["user_id"])
    await db.sesiones.update_many(
        {"user_id": user_id_str, "activa": True},
        {"$set": {"activa": False, "revoked_at": now}},
    )

    return MessageOut(message="Contraseña actualizada exitosamente. Ya puedes iniciar sesión.")
