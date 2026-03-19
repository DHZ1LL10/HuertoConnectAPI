"""
Huerto Connect — Security Utilities
Password hashing (scrypt), OTP generation/verification (HMAC-SHA256),
JWT tokens, magic-link tokens.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from shared.config import settings


# ===================== PASSWORD HASHING =====================

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash a password using scrypt with pepper.
    Returns (hash_hex, salt_hex).
    """
    if salt is None:
        salt = os.urandom(32).hex()

    peppered = f"{password}{settings.AUTH_PASSWORD_PEPPER}"
    salt_bytes = bytes.fromhex(salt)

    derived = hashlib.scrypt(
        peppered.encode("utf-8"),
        salt=salt_bytes,
        n=16384,
        r=8,
        p=1,
        dklen=64,
    )
    return derived.hex(), salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    """Verify a password against its hash using timing-safe comparison."""
    computed_hash, _ = hash_password(password, password_salt)
    return hmac.compare_digest(computed_hash, password_hash)


# ===================== OTP =====================

def generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return f"{secrets.randbelow(900000) + 100000}"


def sanitize_numeric_otp(raw: str) -> str:
    """Strip non-digit characters and return at most 6 digits."""
    return re.sub(r"\D", "", str(raw or ""))[:6]


def hash_otp(otp_code: str, challenge_id: Optional[str] = None) -> str:
    """
    Hash an OTP code using HMAC-SHA256.
    If challenge_id is provided, the HMAC input is 'challengeId:otpCode'
    (compatible with Express magic-link flow).
    """
    if challenge_id:
        data = f"{challenge_id}:{otp_code}"
    else:
        data = otp_code
    return hmac.new(
        settings.OTP_HASH_SECRET.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp(otp_code: str, otp_hash: str, challenge_id: Optional[str] = None) -> bool:
    """Verify an OTP code against its hash using timing-safe comparison."""
    computed = hash_otp(otp_code, challenge_id)
    return hmac.compare_digest(computed, otp_hash)


# ===================== JWT TOKENS =====================

def create_jwt_token(user_id: str, email: str, rol: str) -> str:
    """Create a JWT token for a session."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "rol": rol,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None if invalid."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ===================== SESSION TOKEN =====================

def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """Hash a session/reset token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ===================== RESET TOKEN =====================

def generate_reset_token() -> str:
    """Generate a cryptographically secure reset token."""
    return secrets.token_urlsafe(48)


# ===================== MAGIC-LINK TOKEN =====================

def _to_base64url(data: bytes) -> str:
    """Encode bytes as base64url (URL-safe, no padding)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _from_base64url(s: str) -> bytes:
    """Decode base64url string back to bytes."""
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def create_otp_magic_link_token(
    challenge_id: str,
    otp_code: str,
    purpose: str = "login",
    expires_at: Optional[str] = None,
) -> str:
    """
    Create a signed magic-link token containing challengeId + OTP.
    Format: base64url(JSON payload).base64url(HMAC signature)
    Compatible with the Express magic-link implementation.
    """
    if expires_at:
        try:
            exp_ms = int(datetime.fromisoformat(expires_at).timestamp() * 1000)
        except (ValueError, TypeError):
            exp_ms = int((datetime.now(timezone.utc).timestamp() + 300) * 1000)
    else:
        exp_ms = int((datetime.now(timezone.utc).timestamp() + 300) * 1000)

    payload = {
        "challengeId": challenge_id,
        "otpCode": sanitize_numeric_otp(otp_code),
        "purpose": purpose,
        "exp": exp_ms,
    }

    payload_encoded = _to_base64url(json.dumps(payload).encode("utf-8"))
    signature = hmac.new(
        settings.OTP_LINK_SECRET.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return f"{payload_encoded}.{_to_base64url(signature)}"


def verify_otp_magic_link_token(token: str) -> dict:
    """
    Verify a magic-link token. Returns dict with:
      ok=True, challengeId, otpCode, purpose, expiresAt   (on success)
      ok=False, code='invalid_token'|'expired_or_invalid' (on failure)
    """
    if not isinstance(token, str):
        return {"ok": False, "code": "invalid_token"}

    parts = token.strip().split(".")
    if len(parts) != 2:
        return {"ok": False, "code": "invalid_token"}

    payload_encoded, sig_encoded = parts
    if not payload_encoded or not sig_encoded:
        return {"ok": False, "code": "invalid_token"}

    try:
        candidate_sig = _from_base64url(sig_encoded)
        payload = json.loads(_from_base64url(payload_encoded).decode("utf-8"))
    except Exception:
        return {"ok": False, "code": "invalid_token"}

    expected_sig = hmac.new(
        settings.OTP_LINK_SECRET.encode("utf-8"),
        payload_encoded.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(expected_sig, candidate_sig):
        return {"ok": False, "code": "invalid_token"}

    challenge_id = str(payload.get("challengeId", "")).strip()
    otp_code = sanitize_numeric_otp(payload.get("otpCode", ""))
    purpose = str(payload.get("purpose", "")).strip() or "login"
    exp = payload.get("exp", 0)

    if not challenge_id or len(otp_code) != 6 or not isinstance(exp, (int, float)):
        return {"ok": False, "code": "expired_or_invalid"}

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if exp <= now_ms:
        return {"ok": False, "code": "expired_or_invalid"}

    return {
        "ok": True,
        "challengeId": challenge_id,
        "otpCode": otp_code,
        "purpose": purpose,
        "expiresAt": datetime.fromtimestamp(exp / 1000, tz=timezone.utc).isoformat(),
    }
