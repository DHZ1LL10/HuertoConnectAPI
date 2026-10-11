"""Mongo-backed rate limiting for authentication attempts across workers."""
from datetime import datetime, timezone, timedelta
import hashlib
import time
from fastapi import HTTPException, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.core.database import get_db


async def enforce_auth_rate_limit(request: Request):
    if request.method != "POST" or request.url.path.endswith(("/logout", "/sesiones/revoke-all")):
        return
    identity = request.client.host if request.client else "unknown"
    bucket = int(time.time()) // 60
    key = hashlib.sha256(f"{identity}:{bucket}".encode()).hexdigest()
    db = get_db()
    update = {"$inc": {"attempts": 1}, "$setOnInsert": {"expires_at": datetime.now(timezone.utc) + timedelta(minutes=2)}}
    try:
        record = await db.auth_rate_limits.find_one_and_update({"_id": key}, update, upsert=True, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        record = await db.auth_rate_limits.find_one_and_update({"_id": key}, {"$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER)
    if record["attempts"] > 30:
        raise HTTPException(429, "Demasiadas solicitudes de autenticación. Espera un minuto.", headers={"Retry-After": "60"})
