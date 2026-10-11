"""Persistent OTP challenges with atomic attempts, rotation and single-use consumption."""
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from app.core.config import settings

_COLLECTION = "otp_challenges"

def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"

def hash_otp(otp):
    return hmac.new(settings.OTP_HASH_SECRET.encode(), otp.encode(), "sha256").hexdigest()

def verify_otp(plain, hashed):
    return secrets.compare_digest(hash_otp(plain), hashed)

async def create_challenge(db, data):
    now = datetime.now(timezone.utc)
    # A newly requested code supersedes older codes for the same flow.
    await db[_COLLECTION].delete_many({"email": data.email, "tipo": data.tipo})
    doc = {"tipo": data.tipo, "email": data.email, "otp_hash": data.otp_hash,
           "user_id": data.user_id, "pending_user_data": data.pending_user_data,
           "verify_attempts": 0, "resend_count": 0, "created_at": now, "updated_at": now,
           "expires_at": now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)}
    result = await db[_COLLECTION].insert_one(doc)
    return str(result.inserted_id)

async def get_challenge(db, challenge_id, allow_expired=False):
    if not ObjectId.is_valid(challenge_id):
        raise HTTPException(400, "Challenge ID inválido")
    doc = await db[_COLLECTION].find_one({"_id": ObjectId(challenge_id)})
    if not doc:
        raise HTTPException(404, "El proceso de verificación no existe o ya expiró")
    if not allow_expired and doc["expires_at"].replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(410, "El código OTP expiró. Solicita uno nuevo.")
    return doc

async def validate_and_consume_otp(db, challenge_id, plain_otp):
    original = await get_challenge(db, challenge_id)
    now = datetime.now(timezone.utc)
    doc = await db[_COLLECTION].find_one_and_update(
        {"_id": original["_id"], "expires_at": {"$gt": now}, "verify_attempts": {"$lt": settings.OTP_MAX_ATTEMPTS}},
        {"$inc": {"verify_attempts": 1}, "$set": {"updated_at": now}}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise HTTPException(429, "Código consumido o límite de intentos alcanzado")
    if not verify_otp(plain_otp, doc["otp_hash"]):
        raise HTTPException(401, "Código OTP incorrecto")
    # Compare the hash again: a concurrent resend invalidates the old code.
    consumed = await db[_COLLECTION].find_one_and_delete(
        {"_id": doc["_id"], "otp_hash": doc["otp_hash"], "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if not consumed:
        raise HTTPException(409, "El código ya fue utilizado o reemplazado")
    return consumed

async def regenerate_otp(db, challenge_id):
    doc = await get_challenge(db, challenge_id, allow_expired=True)
    new_otp = generate_otp()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.OTP_EXPIRATION_MINUTES)
    updated = await db[_COLLECTION].find_one_and_update(
        {"_id": doc["_id"], "otp_hash": doc["otp_hash"], "resend_count": {"$lt": settings.OTP_MAX_RESENDS}},
        {"$set": {"otp_hash": hash_otp(new_otp), "verify_attempts": 0, "expires_at": expires, "updated_at": now}, "$inc": {"resend_count": 1}},
        return_document=ReturnDocument.AFTER)
    if not updated:
        raise HTTPException(429, "Límite de reenvíos alcanzado o código reemplazado")
    return new_otp, str(doc["_id"]), expires
