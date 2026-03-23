"""
Auth Service — Router de autenticación con OTP.

Endpoints:
  POST /auth/register   → Registro (fase 1): crea/actualiza usuario no verificado en DB,
                          envía OTP.
  POST /auth/login      → Login (fase 1): valida credenciales, crea challenge login,
                          envía OTP.
  POST /auth/send-otp   → Alias de /auth/login (compatibilidad frontend).
  POST /auth/verify-otp → Verifica OTP:
                            - tipo=registro        → crea user definitivo en DB + sesión + JWT
                            - tipo=login           → crea sesión + JWT
                            - tipo=reset-password  → genera token de un solo uso
  POST /auth/resend-otp → Regenera y reenvía OTP (máx. 3 veces).

Todos los errores siguen los códigos HTTP estándar:
  400 Bad Request · 401 Unauthorized · 404 Not Found · 409 Conflict · 429 Too Many Requests
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import (
    ChallengeTipo,
    OtpChallengeCreate,
    UserInDB,
    UserRole,
    UserEstado,
    AuthProvider,
)
from app.services import otp_service
from app.services.mail_adapter import send_otp_background
from app.services.mail_service import mask_email

router = APIRouter(prefix="/auth", tags=["Auth OTP"])


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _mask(email: str) -> str:
    return mask_email(email)


async def _create_session(db, user_id: str, request: Request) -> tuple[str, str, str]:
    """
    Crea un documento de sesión en MongoDB y genera el JWT.

    Returns:
        Tupla ``(jwt_token, jti, expires_iso)``.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    token = create_access_token({
        "sub": user_id,
        "jti": jti,
    })

    session_doc = {
        "user_id": user_id,
        "jti": jti,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "dispositivo": request.headers.get("x-device", "web"),
        "created_at": now,
        "expires_at": expires_at,
        "activa": True,
        "revoked_at": None,
    }
    await db.sesiones.insert_one(session_doc)
    return token, jti, expires_at.isoformat()


# ---------------------------------------------------------------------------
# Request / Response schemas locales
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    apellidos: str = Field(default="", max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    confirm_password: str = Field(default="", max_length=128, alias="confirmPassword")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "nombre": "Ana",
                "apellidos": "Garcia",
                "email": "ana.garcia@huertoconnect.com",
                "password": "MiPass2026!",
                "confirmPassword": "MiPass2026!",
            }
        },
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "ana.garcia@huertoconnect.com",
                "password": "MiPass2026!",
            }
        }
    }


class VerifyOtpRequest(BaseModel):
    challenge_id: str = Field(..., alias="challengeId")
    otp_code: str = Field(..., alias="otpCode", pattern=r"^\d{6}$")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "challengeId": "65f3a2018f8f6d66ad4b8123",
                "otpCode": "123456",
            }
        },
    }


class ResendOtpRequest(BaseModel):
    challenge_id: str = Field(..., alias="challengeId")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "challengeId": "65f3a2018f8f6d66ad4b8123",
            }
        },
    }


class ChallengeOut(BaseModel):
    message: str
    challenge_id: str = Field(..., alias="challengeId")
    expires_at: str = Field(..., alias="expiresAt")
    masked_email: str = Field(..., alias="maskedEmail")
    dev_otp_code: Optional[str] = Field(default=None, alias="devOtpCode")

    model_config = {
        "populate_by_name": True,
        "by_alias": True,
        "json_schema_extra": {
            "example": {
                "message": "Código OTP enviado al correo electrónico.",
                "challengeId": "65f3a2018f8f6d66ad4b8123",
                "expiresAt": "2026-03-21T20:10:00+00:00",
                "maskedEmail": "an***@huertoconnect.com",
                "devOtpCode": "123456",
            }
        },
    }


class AuthOut(BaseModel):
    message: str
    token: str
    expires_at: str = Field(..., alias="expiresAt")
    user_id: str = Field(..., alias="userId")

    model_config = {
        "populate_by_name": True,
        "by_alias": True,
        "json_schema_extra": {
            "example": {
                "message": "Inicio de sesión exitoso.",
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "expiresAt": "2026-03-22T02:00:00+00:00",
                "userId": "65f2d6ea9f3d2a3e8a7b9c10",
            }
        },
    }


class ResetTokenOut(BaseModel):
    message: str
    reset_token: str = Field(..., alias="resetToken")

    model_config = {
        "populate_by_name": True,
        "by_alias": True,
        "json_schema_extra": {
            "example": {
                "message": "Código verificado. Ya puedes actualizar tu contraseña.",
                "resetToken": "Y3tiU2YHq8E3Qn3xY5v2xwW6o8nZ9K2hPqM1fR4sT",
            }
        },
    }


class VerifyOtpResponse(BaseModel):
    """Union response for verify-otp — can be login/register (with token) or reset-password (with resetToken)."""
    message: str
    token: Optional[str] = None
    expires_at: Optional[str] = Field(default=None, alias="expiresAt")
    user_id: Optional[str] = Field(default=None, alias="userId")
    reset_token: Optional[str] = Field(default=None, alias="resetToken")

    model_config = {
        "populate_by_name": True,
        "by_alias": True,
        "json_schema_extra": {
            "examples": [
                {
                    "message": "Inicio de sesión exitoso.",
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "expiresAt": "2026-03-22T02:00:00+00:00",
                    "userId": "65f2d6ea9f3d2a3e8a7b9c10",
                },
                {
                    "message": "Código verificado. Ya puedes actualizar tu contraseña.",
                    "resetToken": "Y3tiU2YHq8E3Qn3xY5v2xwW6o8nZ9K2hPqM1fR4sT",
                },
            ]
        },
    }


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=ChallengeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registro — paso 1 (envía OTP)",
)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Crea (o actualiza si existe sin verificar) el usuario en BD con
    ``email_verificado=False`` y envía un OTP de verificación.
    """
    if body.confirm_password and body.password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas no coinciden.",
        )

    db = get_db()

    email = body.email.lower().strip()
    now = datetime.now(timezone.utc)
    pw_hash = hash_password(body.password)

    existing = await db.usuarios.find_one({"email": email})
    if (
        existing
        and existing.get("deleted_at") is None
        and existing.get("email_verificado", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo electrónico.",
        )

    if existing:
        # Permite retomar registro de cuentas no verificadas.
        user_oid = existing["_id"]
        await db.usuarios.update_one(
            {"_id": user_oid},
            {"$set": {
                "nombre": body.nombre.strip(),
                "apellidos": body.apellidos.strip(),
                "password_hash": pw_hash,
                "role": UserRole.usuario,
                "auth_provider": AuthProvider.email,
                "estado": UserEstado.activo,
                "email_verificado": False,
                "updated_at": now,
                "deleted_at": None,
            }},
        )
    else:
        new_user_doc = {
            "nombre": body.nombre.strip(),
            "apellidos": body.apellidos.strip(),
            "email": email,
            "password_hash": pw_hash,
            "role": UserRole.usuario,
            "auth_provider": AuthProvider.email,
            "estado": UserEstado.activo,
            "email_verificado": False,
            "google_id": None,
            "profile_picture": None,
            "region_id": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        result = await db.usuarios.insert_one(new_user_doc)
        user_oid = result.inserted_id

    # Generar OTP y crear challenge
    otp_code = otp_service.generate_otp()
    otp_hash = otp_service.hash_otp(otp_code)

    challenge_data = OtpChallengeCreate(
        tipo=ChallengeTipo.registro,
        email=email,
        otp_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        user_id=str(user_oid),
    )
    challenge_id = await otp_service.create_challenge(db, challenge_data)

    # Enviar correo en background
    full_name = f"{body.nombre} {body.apellidos}".strip()
    await send_otp_background(
        background_tasks,
        email=body.email,
        otp_code=otp_code,
        tipo="registro",
        recipient_name=full_name,
        challenge_id=challenge_id,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )

    # Exponer código en respuesta solo en modo dev
    response = ChallengeOut(
        message="Código de verificación enviado al correo electrónico.",
        challengeId=challenge_id,
        expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        maskedEmail=_mask(body.email),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.dev_otp_code = otp_code

    return response


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=ChallengeOut,
    summary="Login — paso 1 (envía OTP)",
)
async def login(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Valida email + contraseña y envía un OTP para la verificación 2FA.
    """
    db = get_db()

    user = await db.usuarios.find_one({
        "email": body.email.lower(),
        "deleted_at": None,
    })

    # Mismo mensaje genérico para email no encontrado o contraseña incorrecta
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    if user.get("estado") != "Activo":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva o suspendida.",
        )

    if not user.get("email_verificado", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta aún no está verificada. Regístrate de nuevo para recibir un código.",
        )

    # Crear challenge login
    otp_code = otp_service.generate_otp()
    otp_hash = otp_service.hash_otp(otp_code)

    challenge_data = OtpChallengeCreate(
        tipo=ChallengeTipo.login,
        email=user["email"],
        otp_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        user_id=str(user["_id"]),
    )
    challenge_id = await otp_service.create_challenge(db, challenge_data)

    # Nombre para el saludo del email
    full_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))

    await send_otp_background(
        background_tasks,
        email=user["email"],
        otp_code=otp_code,
        tipo="login",
        recipient_name=full_name,
        challenge_id=challenge_id,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )

    response = ChallengeOut(
        message="Código OTP enviado al correo electrónico.",
        challengeId=challenge_id,
        expiresAt=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        maskedEmail=_mask(user["email"]),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.dev_otp_code = otp_code

    return response


# ---------------------------------------------------------------------------
# POST /auth/send-otp — alias de login (compatibilidad frontend)
# ---------------------------------------------------------------------------

@router.post(
    "/send-otp",
    response_model=ChallengeOut,
    summary="Login — alias de /auth/login",
)
async def send_otp(
    body: LoginRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Alias de /auth/login para compatibilidad con frontend."""
    return await login(body, background_tasks, request)


# ---------------------------------------------------------------------------
# POST /auth/verify-otp
# ---------------------------------------------------------------------------

_RESET_COLLECTION = "password_resets"
_RESET_EXPIRE_MINUTES = 10


@router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    summary="Verifica OTP y devuelve JWT o resetToken",
)
async def verify_otp(
    body: VerifyOtpRequest,
    request: Request,
):
    """
    Verifica el código OTP recibido por correo.

    - Tipo **registro** → verifica/activa el usuario registrado y abre sesión.
    - Tipo **login**    → recupera el usuario existente y abre sesión.
    - Tipo **reset-password** → genera un token de un solo uso para cambiar contraseña.

    Devuelve un JWT de acceso junto con el ID del usuario, o un resetToken.
    """
    db = get_db()
    challenge = await otp_service.validate_and_consume_otp(db, body.challenge_id, body.otp_code)

    tipo = challenge["tipo"]
    now = datetime.now(timezone.utc)

    if tipo == ChallengeTipo.registro or tipo == "registro":
        # ---- Verificar/activar usuario registrado ----
        raw_uid = challenge.get("user_id")
        user_id = None

        if raw_uid:
            try:
                user_oid = ObjectId(raw_uid)
            except Exception:
                user_oid = None

            if user_oid:
                user = await db.usuarios.find_one({"_id": user_oid, "deleted_at": None})
                if user:
                    await db.usuarios.update_one(
                        {"_id": user_oid},
                        {"$set": {
                            "email_verificado": True,
                            "estado": UserEstado.activo,
                            "ultima_actividad": now,
                            "updated_at": now,
                        }},
                    )
                    user_id = str(user_oid)

        # Compatibilidad con challenges antiguos que traían pending_user_data.
        if not user_id:
            pending = challenge.get("pending_user_data", {})
            if not pending:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Datos de registro no encontrados en el challenge.",
                )

            existing = await db.usuarios.find_one({"email": pending["email"], "deleted_at": None})
            if existing:
                await db.usuarios.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "email_verificado": True,
                        "estado": UserEstado.activo,
                        "ultima_actividad": now,
                        "updated_at": now,
                    }},
                )
                user_id = str(existing["_id"])
            else:
                new_user_doc = {
                    "nombre": pending["nombre"],
                    "apellidos": pending.get("apellidos", ""),
                    "email": pending["email"],
                    "password_hash": pending["password_hash"],
                    "role": UserRole.usuario,
                    "auth_provider": AuthProvider.email,
                    "estado": UserEstado.activo,
                    "email_verificado": True,
                    "google_id": None,
                    "profile_picture": None,
                    "region_id": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
                result = await db.usuarios.insert_one(new_user_doc)
                user_id = str(result.inserted_id)

        # Crear sesión y JWT
        token, jti, expires_iso = await _create_session(db, user_id, request)
        return VerifyOtpResponse(
            message="Cuenta verificada exitosamente.",
            token=token,
            expiresAt=expires_iso,
            userId=user_id,
        )

    elif tipo == ChallengeTipo.login or tipo == "login":
        # ---- Recuperar usuario existente ----
        raw_uid = challenge.get("user_id")
        if not raw_uid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Challenge de login sin user_id.",
            )
        user_id = raw_uid
        # Actualizar última actividad
        await db.usuarios.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"ultima_actividad": now}},
        )

        # Crear sesión y JWT
        token, jti, expires_iso = await _create_session(db, user_id, request)
        return VerifyOtpResponse(
            message="Inicio de sesión exitoso.",
            token=token,
            expiresAt=expires_iso,
            userId=user_id,
        )

    elif tipo in (ChallengeTipo.reset_password, "reset-password", "reset_password"):
        # ---- Generar token de un solo uso para reset-password ----
        raw_reset_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_reset_token.encode()).hexdigest()
        expires_reset = now + timedelta(minutes=_RESET_EXPIRE_MINUTES)

        reset_doc = {
            "user_id": challenge.get("user_id"),
            "token_hash": token_hash,
            "expires_at": expires_reset,
            "used_at": None,
            "created_at": now,
        }
        await db[_RESET_COLLECTION].insert_one(reset_doc)

        return VerifyOtpResponse(
            message="Código verificado. Ya puedes actualizar tu contraseña.",
            resetToken=raw_reset_token,
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de challenge no soportado en este endpoint: {tipo}",
        )


# ---------------------------------------------------------------------------
# POST /auth/resend-otp
# ---------------------------------------------------------------------------

@router.post(
    "/resend-otp",
    response_model=ChallengeOut,
    summary="Reenvía el código OTP (máx. 3 veces)",
)
async def resend_otp(
    body: ResendOtpRequest,
    background_tasks: BackgroundTasks,
):
    """
    Genera un nuevo código OTP para el challenge activo y lo reenvía por correo.
    Límite: 3 reenvíos por challenge.
    """
    db = get_db()
    new_otp, challenge_id, new_expires = await otp_service.regenerate_otp(db, body.challenge_id)

    # Recuperar el challenge para obtener el email y tipo
    doc = await db.otp_challenges.find_one({"_id": ObjectId(challenge_id)})
    email = doc.get("email", "")
    tipo = doc.get("tipo", "login")

    # Nombre del destinatario (disponible si es login; en registro está en pending_user_data)
    recipient_name = ""
    if doc.get("user_id"):
        user = await db.usuarios.find_one({"_id": ObjectId(doc["user_id"])})
        if user:
            recipient_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))
    elif doc.get("pending_user_data"):
        pd = doc["pending_user_data"]
        recipient_name = " ".join(filter(None, [pd.get("nombre", ""), pd.get("apellidos", "")])).strip()

    await send_otp_background(
        background_tasks,
        email=email,
        otp_code=new_otp,
        tipo=tipo,
        recipient_name=recipient_name,
        challenge_id=challenge_id,
        expires_at=new_expires.isoformat(),
    )

    response = ChallengeOut(
        message="Nuevo código OTP enviado correctamente.",
        challengeId=challenge_id,
        expiresAt=new_expires.isoformat(),
        maskedEmail=_mask(email),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.dev_otp_code = new_otp

    return response
