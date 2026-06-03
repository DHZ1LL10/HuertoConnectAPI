"""
Auth Service — Exports centralizados de modelos y schemas.

Importa desde aquí para mantener rutas de importación limpias:

    from app.models import UserInDB, UserResponse, ChallengeResponse, ...
"""

# User
from app.models.user import (
    AuthProvider,
    UserCreate,
    UserEstado,
    UserInDB,
    UserResponse,
    UserRole,
    UserUpdate,
)

# OTP Challenge
from app.models.otp_challenge import (
    ChallengeTipo,
    ChallengeResponse,
    OtpChallenge,
    OtpChallengeCreate,
    OTP_MAX_RESENDS,
    OTP_MAX_VERIFY_ATTEMPTS,
    ResendOtpRequest,
    VerifyOtpRequest,
)

# Session
from app.models.session import (
    RevokeSessionRequest,
    Session,
    SessionInfo,
    SessionResponse,
    SessionTokenResponse,
)

# Password Reset
from app.models.password_reset import (
    ForgotPasswordRequest,
    PASSWORD_RESET_EXPIRE_MINUTES,
    PasswordReset,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ResetTokenResponse,
)

__all__ = [
    # User
    "AuthProvider",
    "UserCreate",
    "UserEstado",
    "UserInDB",
    "UserResponse",
    "UserRole",
    "UserUpdate",
    # OTP Challenge
    "ChallengeTipo",
    "ChallengeResponse",
    "OtpChallenge",
    "OtpChallengeCreate",
    "OTP_MAX_RESENDS",
    "OTP_MAX_VERIFY_ATTEMPTS",
    "ResendOtpRequest",
    "VerifyOtpRequest",
    # Session
    "RevokeSessionRequest",
    "Session",
    "SessionInfo",
    "SessionResponse",
    "SessionTokenResponse",
    # Password Reset
    "ForgotPasswordRequest",
    "PASSWORD_RESET_EXPIRE_MINUTES",
    "PasswordReset",
    "ResetPasswordRequest",
    "ResetPasswordResponse",
    "ResetTokenResponse",
]
