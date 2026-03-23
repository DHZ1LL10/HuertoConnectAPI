"""
Auth Service — Servicio de OTP.

Implementa generación, hasheo, verificación y control de intentos/reenvíos
para el flujo de verificación en dos pasos (registro, login, reset-password).

Todas las operaciones de BD reciben la instancia de Motor DB como parámetro
para facilitar el testing y evitar estado global.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.models import (
    ChallengeTipo,
    OtpChallenge,
    OtpChallengeCreate,
    OTP_MAX_VERIFY_ATTEMPTS,
    OTP_MAX_RESENDS,
)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

OTP_EXPIRATION_MINUTES: int = getattr(settings, "OTP_EXPIRATION_MINUTES", 5)
_COLLECTION = "otp_challenges"


# ---------------------------------------------------------------------------
# OTP — generación y hashing
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """
    Genera un código OTP de 6 dígitos criptográficamente seguro.

    Usa ``secrets.randbelow`` para garantizar uniformidad estadística.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    """
    Devuelve el hash SHA-256 del código OTP.

    El OTP nunca se almacena en claro; solo su hash viaja a MongoDB.
    """
    return hashlib.sha256(otp.encode()).hexdigest()


def verify_otp(plain: str, hashed: str) -> bool:
    """
    Compara el código OTP en texto plano contra su hash almacenado.

    Usa ``secrets.compare_digest`` para prevenir ataques de timing.
    """
    return secrets.compare_digest(hash_otp(plain), hashed)


# ---------------------------------------------------------------------------
# Gestión de challenges en MongoDB
# ---------------------------------------------------------------------------

async def create_challenge(db: AsyncIOMotorDatabase, data: OtpChallengeCreate) -> str:
    """
    Inserta un nuevo ``OtpChallenge`` en MongoDB.

    Returns:
        El ID del documento insertado como string.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=OTP_EXPIRATION_MINUTES)

    doc = {
        "tipo": data.tipo,
        "email": data.email,
        "otp_hash": data.otp_hash,
        "user_id": data.user_id,
        "pending_user_data": data.pending_user_data,
        "verify_attempts": 0,
        "resend_count": 0,
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[_COLLECTION].insert_one(doc)
    return str(result.inserted_id)


async def get_challenge(db: AsyncIOMotorDatabase, challenge_id: str) -> dict:
    """
    Recupera un challenge por su ID y valida que no esté expirado.

    Raises:
        HTTPException 404: challenge no encontrado.
        HTTPException 410: challenge expirado.
    """
    try:
        oid = ObjectId(challenge_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge ID inválido.",
        )

    doc = await db[_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El proceso de verificación no existe o ya expiró.",
        )

    if doc["expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="El código OTP expiró. Solicita uno nuevo.",
        )

    return doc


async def validate_and_consume_otp(
    db: AsyncIOMotorDatabase, challenge_id: str, plain_otp: str
) -> dict:
    """
    Verifica el OTP del challenge y lo consume (elimina) si es correcto.

    Flujo:
    1. Obtiene el challenge (valida existencia y expiración).
    2. Comprueba límite de intentos.
    3. Incrementa ``verify_attempts``.
    4. Verifica el hash.
    5. Si correcto → elimina el challenge y lo devuelve.

    Returns:
        El documento del challenge verificado.

    Raises:
        HTTPException 429: demasiados intentos.
        HTTPException 401: código incorrecto.
    """
    doc = await get_challenge(db, challenge_id)
    oid = doc["_id"]

    # Bloqueo por intentos
    if doc["verify_attempts"] >= OTP_MAX_VERIFY_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Superaste el límite de intentos. Solicita un nuevo código.",
        )

    # Incrementar intentos antes de verificar (previene timing attacks)
    await db[_COLLECTION].update_one(
        {"_id": oid},
        {"$inc": {"verify_attempts": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
    )

    if not verify_otp(plain_otp, doc["otp_hash"]):
        remaining = max(0, OTP_MAX_VERIFY_ATTEMPTS - doc["verify_attempts"] - 1)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Código OTP incorrecto. Intentos restantes: {remaining}",
        )

    # Eliminar challenge consumido
    await db[_COLLECTION].delete_one({"_id": oid})
    return doc


async def regenerate_otp(db: AsyncIOMotorDatabase, challenge_id: str) -> tuple[str, str, datetime]:
    """
    Regenera el OTP para un challenge existente (resend).

    Returns:
        Tupla ``(otp_plain, challenge_id, new_expires_at)``.

    Raises:
        HTTPException 429: límite de reenvíos alcanzado.
    """
    doc = await get_challenge(db, challenge_id)
    oid = doc["_id"]

    if doc["resend_count"] >= OTP_MAX_RESENDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ya alcanzaste el límite de reenvíos. Inicia el proceso nuevamente.",
        )

    new_otp = generate_otp()
    new_hash = hash_otp(new_otp)
    now = datetime.now(timezone.utc)
    new_expires = now + timedelta(minutes=OTP_EXPIRATION_MINUTES)

    await db[_COLLECTION].update_one(
        {"_id": oid},
        {
            "$set": {
                "otp_hash": new_hash,
                "verify_attempts": 0,
                "expires_at": new_expires,
                "updated_at": now,
            },
            "$inc": {"resend_count": 1},
        },
    )

    return new_otp, str(oid), new_expires
