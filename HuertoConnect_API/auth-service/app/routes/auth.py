"""
Auth Service — Auth routes.
All authentication endpoints matching Express API contracts.
Includes magic-link verification (verify-email-link), OTP flow, password reset.
"""

import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.models.schemas import (
    ChallengeResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OtpLoginResponse,
    OtpRegisterResponse,
    OtpResetResponse,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    SessionInfoResponse,
    SessionResponse,
    UserResponse,
    VerifyOtpRequest,
)
from app.services.mail_service import build_verify_url, mask_email, send_otp_email
from shared.auth.dependencies import get_current_user, require_roles
from shared.auth.security import (
    create_jwt_token,
    generate_otp,
    generate_reset_token,
    generate_session_token,
    hash_otp,
    hash_password,
    hash_token,
    sanitize_numeric_otp,
    verify_otp,
    verify_otp_magic_link_token,
    verify_password,
)
from shared.config import settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _serialize_user(user: dict) -> UserResponse:
    """Convert MongoDB user document to response model."""
    return UserResponse(
        id=str(user["_id"]),
        nombre=user["nombre"],
        apellidos=user.get("apellidos", ""),
        email=user["email"],
        rol=user["rol"],
        estado=user["estado"],
        email_verificado=user.get("email_verificado", False),
        region_id=str(user["region_id"]) if user.get("region_id") else None,
    )


async def _create_session(db, user_id: str, user_email: str, user_rol: str, request: Request) -> dict:
    """Create a new session in MongoDB and return session data."""
    jwt_token = create_jwt_token(user_id, user_email, user_rol)
    token_hashed = hash_token(jwt_token)
    now = datetime.utcnow()
    expires = now + timedelta(hours=settings.JWT_EXPIRATION_HOURS)

    session_doc = {
        "token_hash": token_hashed,
        "usuario_id": ObjectId(user_id),
        "activa": True,
        "expires_at": expires,
        "ultima_actividad": now,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "dispositivo": request.headers.get("x-device", "web"),
        "created_at": now,
        "revoked_at": None,
    }
    await db.sesiones.insert_one(session_doc)
    return {
        "token": jwt_token,
        "expires_at": expires.isoformat(),
    }


def _build_frontend_url(pathname: str, params: dict = None) -> str:
    """Build a URL to the frontend with optional query params."""
    base = settings.FRONTEND_URL.rstrip("/")
    path = pathname if pathname.startswith("/") else f"/{pathname}"
    url = f"{base}{path}"
    if params:
        filtered = {k: str(v) for k, v in params.items() if v is not None and v != ""}
        if filtered:
            url += f"?{urlencode(filtered)}"
    return url


# ===================== SEND OTP (Login Phase 1) =====================

@router.post("/send-otp", response_model=ChallengeResponse)
async def send_otp(body: LoginRequest, request: Request):
    """Login phase 1: validate email+password, send OTP."""
    db = request.app.state.mongodb

    # Find user
    user = await db.usuarios.find_one({
        "email": body.email.lower(),
        "deleted_at": None,
    })
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales invalidas.")

    if user.get("estado") != "Activo":
        raise HTTPException(status_code=403, detail="Cuenta inactiva o suspendida.")

    # Check email verified (matches Express behavior)
    if not user.get("email_verificado", False):
        raise HTTPException(
            status_code=403,
            detail="Tu cuenta aun no esta verificada. Registrate de nuevo para recibir un codigo de verificacion.",
        )

    # Verify password
    if not verify_password(body.password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=401, detail="Credenciales invalidas.")

    # Generate OTP and challenge
    otp_code = generate_otp()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)

    challenge = {
        "usuario_id": user["_id"],
        "tipo": "login",
        "otp_hash": hash_otp(otp_code),
        "verify_attempts": 0,
        "resend_count": 0,
        "challenge_context_json": None,
        "expires_at": expires,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.otp_challenges.insert_one(challenge)
    challenge_id = str(result.inserted_id)

    # Send OTP email with magic link
    user_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))
    await send_otp_email(
        to_email=user["email"],
        otp_code=otp_code,
        action="login",
        recipient_name=user_name,
        challenge_id=challenge_id,
        expires_at=expires.isoformat(),
    )

    response = ChallengeResponse(
        message="Codigo OTP enviado al correo electronico.",
        challengeId=challenge_id,
        expiresAt=expires.isoformat(),
        maskedEmail=mask_email(user["email"]),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.devOtpCode = otp_code

    return response


# ===================== LOGIN (alias for send-otp) =====================

@router.post("/login", response_model=ChallengeResponse)
async def login(body: LoginRequest, request: Request):
    """Iniciar sesion: valida email+password, envia OTP al correo."""
    return await send_otp(body, request)


# ===================== REGISTER (Phase 1) =====================

@router.post("/register", response_model=ChallengeResponse)
async def register(body: RegisterRequest, request: Request):
    """Registration phase 1: validate data, send OTP."""
    db = request.app.state.mongodb

    # Check duplicate email
    existing = await db.usuarios.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo electronico.")

    # Hash password for pending user
    pw_hash, pw_salt = hash_password(body.password)

    # Generate OTP
    otp_code = generate_otp()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)

    pending_user = {
        "nombre": body.nombre,
        "apellidos": body.apellidos,
        "email": body.email.lower(),
        "password_hash": pw_hash,
        "password_salt": pw_salt,
    }

    challenge = {
        "usuario_id": None,
        "tipo": "registro",
        "otp_hash": hash_otp(otp_code),
        "verify_attempts": 0,
        "resend_count": 0,
        "challenge_context_json": json.dumps(pending_user),
        "expires_at": expires,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.otp_challenges.insert_one(challenge)
    challenge_id = str(result.inserted_id)

    # Send OTP email with magic link
    full_name = " ".join(filter(None, [body.nombre, body.apellidos]))
    await send_otp_email(
        to_email=body.email,
        otp_code=otp_code,
        action="registro",
        recipient_name=full_name,
        challenge_id=challenge_id,
        expires_at=expires.isoformat(),
    )

    response = ChallengeResponse(
        message="Codigo de verificacion enviado al correo electronico.",
        challengeId=challenge_id,
        expiresAt=expires.isoformat(),
        maskedEmail=mask_email(body.email),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.devOtpCode = otp_code

    return response


# ===================== VERIFY OTP =====================

async def _process_otp_verification(db, challenge_id: str, otp_code: str, request: Request):
    """
    Core OTP verification logic shared by verify-otp and verify-email-link endpoints.
    Returns the appropriate response dict.
    """
    try:
        challenge = await db.otp_challenges.find_one({"_id": ObjectId(challenge_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Challenge ID invalido.")

    if not challenge:
        raise HTTPException(status_code=404, detail="El proceso de verificacion no existe o ya expiro.")

    now = datetime.utcnow()

    # Check expiration
    if challenge["expires_at"] < now:
        raise HTTPException(
            status_code=410,
            detail="El codigo OTP expiro. Solicita un nuevo codigo.",
        )

    # Check max attempts
    if challenge["verify_attempts"] >= settings.OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Superaste el limite de intentos. Solicita un nuevo codigo.",
        )

    # Increment attempts
    await db.otp_challenges.update_one(
        {"_id": challenge["_id"]},
        {"$inc": {"verify_attempts": 1}, "$set": {"updated_at": now}},
    )

    # Verify OTP
    if not verify_otp(otp_code, challenge["otp_hash"]):
        remaining = max(0, settings.OTP_MAX_ATTEMPTS - challenge["verify_attempts"] - 1)
        raise HTTPException(
            status_code=401,
            detail=f"El codigo OTP es incorrecto. Intentos restantes: {remaining}",
        )

    tipo = challenge["tipo"]

    # ---- LOGIN ----
    if tipo == "login":
        user = await db.usuarios.find_one({"_id": challenge["usuario_id"]})
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        session_data = await _create_session(
            db, str(user["_id"]), user["email"], user["rol"], request
        )

        await db.usuarios.update_one(
            {"_id": user["_id"]},
            {"$set": {"ultima_actividad": now}},
        )

        await db.otp_challenges.delete_one({"_id": challenge["_id"]})

        user_resp = _serialize_user(user)
        return {
            "tipo": "login",
            "response": OtpLoginResponse(
                message="Codigo OTP validado correctamente.",
                session=SessionResponse(
                    token=session_data["token"],
                    expires_at=session_data["expires_at"],
                    user=user_resp,
                ),
                user=user_resp,
            ),
            "session": session_data,
            "user": user_resp,
        }

    # ---- REGISTRATION ----
    elif tipo == "registro":
        pending = json.loads(challenge["challenge_context_json"])

        # Check duplicate again
        existing = await db.usuarios.find_one({"email": pending["email"]})
        if existing:
            raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo electronico.")

        # Create user
        new_user = {
            "nombre": pending["nombre"],
            "apellidos": pending["apellidos"],
            "email": pending["email"],
            "password_hash": pending["password_hash"],
            "password_salt": pending["password_salt"],
            "rol": "Usuario",
            "estado": "Activo",
            "email_verificado": True,
            "region_id": None,
            "ultima_actividad": now,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        result = await db.usuarios.insert_one(new_user)
        new_user["_id"] = result.inserted_id

        session_data = await _create_session(
            db, str(new_user["_id"]), new_user["email"], new_user["rol"], request
        )

        await db.otp_challenges.delete_one({"_id": challenge["_id"]})

        user_resp = _serialize_user(new_user)
        return {
            "tipo": "registro",
            "response": OtpRegisterResponse(
                message="Cuenta creada y verificada exitosamente.",
                session=SessionResponse(
                    token=session_data["token"],
                    expires_at=session_data["expires_at"],
                    user=user_resp,
                ),
                user=user_resp,
            ),
            "session": session_data,
            "user": user_resp,
        }

    # ---- RESET PASSWORD ----
    elif tipo in ("reset_password", "reset-password"):
        raw_reset_token = generate_reset_token()
        hashed_reset_token = hash_token(raw_reset_token)
        expires_reset = now + timedelta(minutes=15)

        reset_doc = {
            "usuario_id": challenge["usuario_id"],
            "token_hash": hashed_reset_token,
            "expires_at": expires_reset,
            "used_at": None,
            "source_challenge_id": challenge["_id"],
            "created_at": now,
        }
        await db.password_resets.insert_one(reset_doc)

        await db.otp_challenges.delete_one({"_id": challenge["_id"]})

        return {
            "tipo": "reset-password",
            "response": OtpResetResponse(
                message="Codigo verificado. Ya puedes actualizar tu contrasena.",
                resetToken=raw_reset_token,
            ),
            "resetToken": raw_reset_token,
        }

    raise HTTPException(status_code=400, detail="Tipo de challenge desconocido.")


@router.post("/verify-otp")
async def verify_otp_endpoint(body: VerifyOtpRequest, request: Request):
    """
    Verify OTP for login, registration, or password reset.
    Response varies by challenge type.
    """
    db = request.app.state.mongodb
    result = await _process_otp_verification(db, body.challengeId, body.otpCode, request)
    return result["response"]


# ===================== RESEND OTP =====================

@router.post("/resend-otp", response_model=ChallengeResponse)
async def resend_otp(body: ResendOtpRequest, request: Request):
    """Resend OTP for any active challenge."""
    db = request.app.state.mongodb

    try:
        challenge = await db.otp_challenges.find_one({"_id": ObjectId(body.challengeId)})
    except Exception:
        raise HTTPException(status_code=400, detail="Challenge ID invalido.")

    if not challenge:
        raise HTTPException(status_code=404, detail="No se encontro un proceso OTP activo.")

    now = datetime.utcnow()

    if challenge["expires_at"] < now:
        raise HTTPException(status_code=410, detail="Challenge expirado.")

    if challenge["resend_count"] >= settings.OTP_MAX_RESENDS:
        raise HTTPException(status_code=429, detail="Ya alcanzaste el limite de reenvios para este codigo.")

    # Generate new OTP
    otp_code = generate_otp()
    otp_hashed = hash_otp(otp_code)
    new_expires = now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)

    await db.otp_challenges.update_one(
        {"_id": challenge["_id"]},
        {
            "$set": {
                "otp_hash": otp_hashed,
                "verify_attempts": 0,
                "expires_at": new_expires,
                "updated_at": now,
            },
            "$inc": {"resend_count": 1},
        },
    )

    # Determine email and name
    email = None
    recipient_name = ""
    tipo = challenge["tipo"]

    if challenge["usuario_id"]:
        user = await db.usuarios.find_one({"_id": challenge["usuario_id"]})
        if user:
            email = user["email"]
            recipient_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))
    elif challenge.get("challenge_context_json"):
        ctx = json.loads(challenge["challenge_context_json"])
        email = ctx.get("email")
        recipient_name = " ".join(filter(None, [ctx.get("nombre", ""), ctx.get("apellidos", "")]))

    challenge_id = str(challenge["_id"])

    if email:
        purpose = "registro" if tipo == "registro" else ("reset-password" if tipo in ("reset_password", "reset-password") else "login")
        await send_otp_email(
            to_email=email,
            otp_code=otp_code,
            action=purpose,
            recipient_name=recipient_name,
            challenge_id=challenge_id,
            expires_at=new_expires.isoformat(),
        )

    msg = (
        "Nuevo codigo de recuperacion enviado correctamente."
        if tipo in ("reset_password", "reset-password")
        else "Nuevo codigo OTP enviado correctamente."
    )

    response = ChallengeResponse(
        message=msg,
        challengeId=challenge_id,
        expiresAt=new_expires.isoformat(),
        maskedEmail=mask_email(email) if email else None,
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.devOtpCode = otp_code

    return response


# ===================== FORGOT PASSWORD =====================

@router.post("/forgot-password", response_model=ChallengeResponse)
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Initiate password recovery via email OTP."""
    db = request.app.state.mongodb

    user = await db.usuarios.find_one({
        "email": body.email.lower(),
        "deleted_at": None,
    })

    now = datetime.utcnow()
    expires = now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)

    # Anti-enumeration: always respond 200
    if not user:
        return ChallengeResponse(
            message="Si el correo esta registrado, recibiras un codigo para cambiar tu contrasena.",
            challengeId="",
            expiresAt=expires.isoformat(),
            maskedEmail=mask_email(body.email),
        )

    otp_code = generate_otp()
    otp_hashed = hash_otp(otp_code)

    challenge = {
        "usuario_id": user["_id"],
        "tipo": "reset-password",
        "otp_hash": otp_hashed,
        "verify_attempts": 0,
        "resend_count": 0,
        "challenge_context_json": None,
        "expires_at": expires,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.otp_challenges.insert_one(challenge)
    challenge_id = str(result.inserted_id)

    user_name = " ".join(filter(None, [user.get("nombre", ""), user.get("apellidos", "")]))
    await send_otp_email(
        to_email=user["email"],
        otp_code=otp_code,
        action="reset-password",
        recipient_name=user_name,
        challenge_id=challenge_id,
        expires_at=expires.isoformat(),
    )

    response = ChallengeResponse(
        message="Codigo para cambio de contrasena enviado al correo electronico.",
        challengeId=challenge_id,
        expiresAt=expires.isoformat(),
        maskedEmail=mask_email(user["email"]),
    )
    if settings.OTP_EXPOSE_CODE_IN_RESPONSE:
        response.devOtpCode = otp_code

    return response


# ===================== RESET PASSWORD =====================

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, request: Request):
    """Change password using a one-time reset token."""
    db = request.app.state.mongodb

    raw_token = body.resetToken or body.token
    if not raw_token:
        raise HTTPException(status_code=400, detail="Token de restablecimiento requerido.")

    hashed = hash_token(raw_token)
    now = datetime.utcnow()

    reset_doc = await db.password_resets.find_one({
        "token_hash": hashed,
        "used_at": None,
    })
    if not reset_doc:
        raise HTTPException(
            status_code=400,
            detail="El enlace de restablecimiento expiro o ya fue usado. Solicita uno nuevo.",
        )

    if reset_doc["expires_at"] < now:
        raise HTTPException(status_code=410, detail="Token expirado.")

    # Update password
    new_hash, new_salt = hash_password(body.newPassword)
    await db.usuarios.update_one(
        {"_id": reset_doc["usuario_id"]},
        {"$set": {
            "password_hash": new_hash,
            "password_salt": new_salt,
            "updated_at": now,
        }},
    )

    # Mark token as used
    await db.password_resets.update_one(
        {"_id": reset_doc["_id"]},
        {"$set": {"used_at": now}},
    )

    # Revoke all active sessions for security
    await db.sesiones.update_many(
        {"usuario_id": reset_doc["usuario_id"], "activa": True},
        {"$set": {"activa": False, "revoked_at": now}},
    )

    return MessageResponse(message="Contrasena actualizada exitosamente. Ya puedes iniciar sesion.")


# ===================== SESSION =====================

@router.get("/session")
async def get_session(current_user: dict = Depends(get_current_user)):
    """Validate current session and return user info."""
    return {
        "message": "Sesion valida",
        "user": current_user,
    }


# ===================== LOGOUT =====================

@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """Revoke current session."""
    db = request.app.state.mongodb
    token = request.headers.get("Authorization", "")[7:]
    token_hashed = hash_token(token)
    now = datetime.utcnow()

    await db.sesiones.update_one(
        {"token_hash": token_hashed},
        {"$set": {"activa": False, "revoked_at": now}},
    )

    return MessageResponse(message="Sesion cerrada.")


# ===================== SESSION MANAGEMENT =====================

@router.get("/sesiones", response_model=list[SessionInfoResponse])
async def list_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all active sessions for the current user."""
    db = request.app.state.mongodb

    sessions = await db.sesiones.find({
        "usuario_id": ObjectId(current_user["id"]),
        "activa": True,
    }).to_list(50)

    return [
        SessionInfoResponse(
            id=str(s["_id"]),
            ip=s.get("ip"),
            user_agent=s.get("user_agent"),
            dispositivo=s.get("dispositivo"),
            ultima_actividad=s.get("ultima_actividad", "").isoformat() if s.get("ultima_actividad") else None,
            created_at=s.get("created_at", "").isoformat() if s.get("created_at") else None,
        )
        for s in sessions
    ]


@router.delete("/sesiones/{session_id}", response_model=MessageResponse)
async def delete_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Close a specific session."""
    db = request.app.state.mongodb
    now = datetime.utcnow()

    result = await db.sesiones.update_one(
        {
            "_id": ObjectId(session_id),
            "usuario_id": ObjectId(current_user["id"]),
            "activa": True,
        },
        {"$set": {"activa": False, "revoked_at": now}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Sesion no encontrada.")

    return MessageResponse(message="Sesion cerrada.")


@router.post("/sesiones/revoke-all", response_model=MessageResponse)
async def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Revoke all sessions except the current one."""
    db = request.app.state.mongodb
    now = datetime.utcnow()

    # Get current token hash
    current_token = request.headers.get("Authorization", "")[7:]
    current_hash = hash_token(current_token)

    await db.sesiones.update_many(
        {
            "usuario_id": ObjectId(current_user["id"]),
            "activa": True,
            "token_hash": {"$ne": current_hash},
        },
        {"$set": {"activa": False, "revoked_at": now}},
    )

    return MessageResponse(message="Todas las demas sesiones han sido cerradas.")


# ===================== VERIFY EMAIL LINK (Magic Link) =====================

from fastapi.responses import RedirectResponse


class VerifyEmailLinkRequest(BaseModel):
    token: str


@router.post("/verify-email-link")
async def verify_email_link_api(body: VerifyEmailLinkRequest, request: Request):
    """
    Verifica un magic-link token enviado por correo (llamada desde el frontend SPA).
    El frontend extrae el token de la URL y lo envía aquí via POST.
    Devuelve la misma respuesta que /verify-otp.
    """
    token_data = verify_otp_magic_link_token(body.token)
    if not token_data.get("ok"):
        raise HTTPException(
            status_code=400,
            detail="El enlace es invalido o ya expiro. Solicita un nuevo codigo.",
        )

    db = request.app.state.mongodb
    result = await _process_otp_verification(
        db, token_data["challengeId"], token_data["otpCode"], request
    )
    response = result["response"]
    # Añadir tipo al payload para que el frontend pueda decidir la redirección
    if hasattr(response, "__dict__"):
        response.__dict__["tipo"] = result.get("tipo")
    return response


@router.get("/verify-email-link")
async def verify_email_link_redirect(token: str, request: Request):
    """
    Verifica un magic-link token y redirige al frontend con el resultado.
    Este endpoint es el destino del botón del correo OTP.
    """
    frontend_login = settings.FRONTEND_URL.rstrip("/") + settings.FRONTEND_LOGIN_PATH
    frontend_dashboard = settings.FRONTEND_URL.rstrip("/") + settings.FRONTEND_DASHBOARD_PATH

    def error_redirect(code: str, message: str) -> RedirectResponse:
        params = urlencode({
            "source": "email-link",
            "magicLinkStatus": "error",
            "magicLinkCode": code,
            "magicLinkMessage": message,
        })
        return RedirectResponse(url=f"{frontend_login}?{params}", status_code=302)

    if not token:
        return error_redirect("missing_token", "El enlace es invalido o incompleto.")

    token_data = verify_otp_magic_link_token(token)
    if not token_data.get("ok"):
        return error_redirect(
            token_data.get("code", "invalid_token"),
            "El enlace expiro o no es valido. Solicita un nuevo codigo.",
        )

    db = request.app.state.mongodb
    try:
        result = await _process_otp_verification(
            db, token_data["challengeId"], token_data["otpCode"], request
        )
    except HTTPException as exc:
        return error_redirect("cannot_complete", exc.detail)

    tipo = result.get("tipo", "login")

    if tipo == "reset-password":
        reset_token = result.get("resetToken", "")
        params = urlencode({
            "source": "email-link",
            "magicLinkStatus": "ok",
            "magicLinkType": "reset-password",
            "flow": "forgot-reset",
            "resetToken": reset_token,
        })
        return RedirectResponse(url=f"{frontend_login}?{params}", status_code=302)

    # login or registro — pass session token to frontend
    session = result.get("session", {})
    user = result.get("user")
    params = {
        "source": "email-link",
        "magicLinkStatus": "ok",
        "magicLinkType": tipo,
        "flow": "magic-login",
        "redirectTo": settings.FRONTEND_DASHBOARD_PATH,
        "sessionToken": session.get("token", ""),
        "sessionExpiresAt": session.get("expires_at", ""),
    }
    if user:
        params["userId"] = getattr(user, "id", "")
        params["userEmail"] = getattr(user, "email", "")
        params["userName"] = getattr(user, "nombre", "")
        params["userRole"] = getattr(user, "rol", "")
    filtered = {k: str(v) for k, v in params.items() if v}
    return RedirectResponse(
        url=f"{frontend_login}?{urlencode(filtered)}", status_code=302
    )
