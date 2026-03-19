"""
Auth Service — Pydantic models for request/response validation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


# ===================== REQUEST MODELS =====================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    confirmPassword: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirmPassword:
            raise ValueError("Las contrasenas no coinciden.")
        return self


class RegisterRequest(BaseModel):
    nombre: str = Field(..., min_length=1)
    apellidos: str = ""
    email: EmailStr
    password: str = Field(..., min_length=6)
    confirmPassword: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirmPassword:
            raise ValueError("Las contrasenas no coinciden.")
        return self


class VerifyOtpRequest(BaseModel):
    challengeId: str
    otpCode: str = Field(..., pattern=r"^\d{6}$")


class ResendOtpRequest(BaseModel):
    challengeId: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    resetToken: Optional[str] = None
    token: Optional[str] = None  # backwards compat
    newPassword: str = Field(..., min_length=6)


# ===================== RESPONSE MODELS =====================

class UserResponse(BaseModel):
    id: str
    nombre: str
    apellidos: str = ""
    email: str
    rol: str
    estado: str
    email_verificado: bool = False
    region_id: Optional[str] = None


class SessionResponse(BaseModel):
    token: str
    expires_at: str
    user: UserResponse


class ChallengeResponse(BaseModel):
    message: str
    challengeId: str
    expiresAt: str
    maskedEmail: Optional[str] = None
    devOtpCode: Optional[str] = None


class OtpLoginResponse(BaseModel):
    message: str
    session: SessionResponse
    user: UserResponse


class OtpRegisterResponse(BaseModel):
    message: str
    session: SessionResponse
    user: UserResponse


class OtpResetResponse(BaseModel):
    message: str
    resetToken: str


class MessageResponse(BaseModel):
    message: str


class SessionInfoResponse(BaseModel):
    id: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    dispositivo: Optional[str] = None
    ultima_actividad: Optional[str] = None
    created_at: Optional[str] = None
