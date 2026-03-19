"""
Auth Service — Router de autenticación con OTP.

Endpoints:
  POST /auth/register   → Registro (fase 1): valida email único, hashea password,
                          guarda pending_user_data en otp_challenges, envía OTP.
  POST /auth/login      → Login (fase 1): valida credenciales, crea challenge login,
                          envía OTP.
  POST /auth/verify-otp → Verifica OTP:
                            - tipo=registro → crea user definitivo en DB + sesión + JWT
                            - tipo=login    → crea sesión + JWT
  POST /auth/resend-otp → Regenera y reenvía OTP (máx. 3 veces).

Todos los errores siguen los códigos HTTP estándar:
  400 Bad Request · 401 Unauthorized · 404 Not Found · 409 Conflict · 429 Too Many Requests
"""

import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
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
    confirm_password: str = Field(..., min_length=6, max_length=128, alias="confirmPassword")

    model_config = {"populate_by_name": True}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class VerifyOtpRequest(BaseModel):
    challenge_id: str = Field(..., alias="challengeId")
    otp_code: str = Field(..., alias="otpCode", pattern=r"^\d{6}$")

    model_config = {"populate_by_name": True}


class ResendOtpRequest(BaseModel):
    challenge_id: str = Field(..., alias="challengeId")

    model_config = {"populate_by_name": True}


class ChallengeOut(BaseModel):
    message: str
    challenge_id: str = Field(..., alias="challengeId")
    expires_at: str = Field(..., alias="expiresAt")
    masked_email: str = Field(..., alias="maskedEmail")

    model_config = {"populate_by_name": True}


class AuthOut(BaseModel):
    message: str
    token: str
    expires_at: str = Field(..., alias="expiresAt")
    user_id: str = Field(..., alias="userId")

    model_config = {"populate_by_name": True}


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
    Valida email único, hashea la contraseña y envía un OTP de verificación.
    El usuario **no** se crea en BD hasta que el OTP sea confirmado.
    """
    if body.password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas no coinciden.",
        )

    db = get_db()

    # Email único
    existing = await db.usuarios.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo electrónico.",
        )

    # Hashear contraseña y preparar datos pendientes
    pw_hash = hash_password(body.password)
    pending_data = {
        "nombre": body.nombre,
        "apellidos": body.apellidos,
        "email": body.email.lower(),
        "password_hash": pw_hash,
    }

    # Generar OTP y crear challenge
    otp_code = otp_service.generate_otp()
    otp_hash = otp_service.hash_otp(otp_code)

    challenge_data = OtpChallengeCreate(
        tipo=ChallengeTipo.registro,
        email=body.email.lower(),
        otp_hash=otp_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        pending_user_data=pending_data,
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
    # Dev helper
    if getattr(settings, "OTP_EXPOSE_CODE_IN_RESPONSE", False):
        response.__dict__["devOtpCode"] = otp_code

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
    # (anti-enumeración)
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
    if getattr(settings, "OTP_EXPOSE_CODE_IN_RESPONSE", False):
        response.__dict__["devOtpCode"] = otp_code

    return response


# ---------------------------------------------------------------------------
# POST /auth/verify-otp
# ---------------------------------------------------------------------------

@router.post(
    "/verify-otp",
    response_model=AuthOut,
    summary="Verifica OTP y devuelve JWT",
)
async def verify_otp(
    body: VerifyOtpRequest,
    request: Request,
):
    """
    Verifica el código OTP recibido por correo.

    - Tipo **registro** → crea el usuario definitivo en BD y abre sesión.
    - Tipo **login**    → recupera el usuario existente y abre sesión.

    Devuelve un JWT de acceso junto con el ID del usuario.
    """
    db = get_db()
    challenge = await otp_service.validate_and_consume_otp(db, body.challenge_id, body.otp_code)

    tipo = challenge["tipo"]
    now = datetime.now(timezone.utc)

    if tipo == ChallengeTipo.registro or tipo == "registro":
        # ---- Crear usuario definitivo ----
        pending = challenge.get("pending_user_data", {})
        if not pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Datos de registro no encontrados en el challenge.",
            )

        # Doble check: evitar race conditions
        existing = await db.usuarios.find_one({"email": pending["email"]})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con ese correo electrónico.",
            )

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

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de challenge no soportado en este endpoint: {tipo}",
        )

    # Crear sesión y JWT
    token, jti, expires_iso = await _create_session(db, user_id, request)

    msg = "Cuenta creada y verificada exitosamente." if tipo in ("registro", ChallengeTipo.registro) \
        else "Inicio de sesión exitoso."

    return AuthOut(
        message=msg,
        token=token,
        expiresAt=expires_iso,
        userId=user_id,
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

    return ChallengeOut(
        message="Nuevo código OTP enviado correctamente.",
        challengeId=challenge_id,
        expiresAt=new_expires.isoformat(),
        maskedEmail=_mask(email),
    )
