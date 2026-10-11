"""
Huerto Connect — Shared Configuration
Centralized settings via Pydantic Settings + environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, model_validator
from typing import Optional


class Settings(BaseSettings):
    """Centralized configuration for all microservices."""

    # --- General ---
    API_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:4200"
    FRONTEND_ORIGIN: str = "http://localhost:4200"
    FRONTEND_LOGIN_PATH: str = "/login"
    FRONTEND_DASHBOARD_PATH: str = "/admin"
    API_PUBLIC_URL: str = "http://localhost:8001"

    # --- MongoDB ---
    MONGO_URI: str = Field(default="mongodb://localhost:27017", validation_alias=AliasChoices("MONGO_URI", "MONGO_URL"))
    MONGO_DB: str = "huerto_connect"

    # --- PostgreSQL ---
    POSTGRES_URI: str = "postgresql://localhost/huerto_connect_ai"

    # --- JWT ---
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8

    # --- OTP ---
    OTP_HASH_SECRET: str = Field(min_length=32)
    OTP_LINK_SECRET: str = ""
    OTP_EXPIRATION_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5
    OTP_MAX_RESENDS: int = 3
    OTP_DELIVERY_MODE: str = "smtp"
    OTP_EXPOSE_CODE_IN_RESPONSE: bool = False

    # --- SMTP ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_SECURE: bool = True
    SMTP_USER: str = "huertoconnect@gmail.com"
    SMTP_APP_PASSWORD: str = ""
    CONTACT_INBOX_EMAIL: str = "huertoconnec@gmail.com"

    IMAGE_STORAGE_PROVIDER: str = "imagekit"
    IMAGEKIT_PRIVATE_KEY: str = Field(default="", repr=False)
    IMAGEKIT_PUBLIC_KEY: str = ""

    # --- Password ---
    AUTH_PASSWORD_PEPPER: str = ""

    # --- Admin Seed ---
    ADMIN_EMAIL: str = "admin@huertoconnect.com"
    ADMIN_PASSWORD: str = ""
    ADMIN_NOMBRE: str = "Administrador"
    ADMIN_APELLIDOS: str = "Sistema"

    # --- Service URLs (for gateway) ---
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    HUERTOS_SERVICE_URL: str = "http://huertos-service:8002"
    PLAGAS_SERVICE_URL: str = "http://plagas-service:8003"
    CHAT_SERVICE_URL: str = "http://chat-service:8004"
    REPORTES_SERVICE_URL: str = "http://reportes-service:8005"
    AGENT_SERVICE_URL: str = "http://agent-service:8006"

    # Internal API key that the gateway injects when forwarding requests to agent-service.
    # Must match APP_API_KEY in docker-compose.yml for agent-service.
    AGENT_API_KEY: str = Field(min_length=32)

    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:4200"
    PLAGUE_MODEL_PATH: str = ""
    DISEASE_MODEL_PATH: str = ""
    RF_MODEL_PATH: str = ""
    AI_DEVICE: str = "cpu"
    AI_MAX_IMAGE_BYTES: int = 10 * 1024 * 1024
    AI_MIN_CONFIDENCE: float = Field(default=0.70, ge=0, le=1)
    AI_MIN_MARGIN: float = Field(default=0.12, ge=0, le=1)
    AGENT_TIMEOUT_SECONDS: float = 130

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    @property
    def cors_origins(self) -> list[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]

    @model_validator(mode="after")
    def validate_security(self):
        if not self.OTP_LINK_SECRET:
            import hmac
            self.OTP_LINK_SECRET = hmac.new(self.OTP_HASH_SECRET.encode(), b"huerto-magic-link", "sha256").hexdigest()
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS debe contener orígenes explícitos")
        if self.ENVIRONMENT == "production" and self.OTP_EXPOSE_CODE_IN_RESPONSE:
            raise ValueError("No exponer OTP en producción")
        return self


settings = Settings()
