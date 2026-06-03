"""
Huerto Connect — Shared Configuration
Centralized settings via Pydantic Settings + environment variables.
"""

from pydantic_settings import BaseSettings
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
    MONGO_URI: str = "mongodb://huerto_admin:huerto_secret_2026@mongodb:27017/huerto_connect?authSource=admin"
    MONGO_DB: str = "huerto_connect"

    # --- PostgreSQL ---
    POSTGRES_URI: str = "postgresql://huerto_pg_admin:huerto_pg_secret_2026@postgres:5432/huerto_connect_ai"

    # --- JWT ---
    JWT_SECRET: str = "change-me-to-a-very-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8

    # --- OTP ---
    OTP_HASH_SECRET: str = "change-me-otp-secret"
    OTP_LINK_SECRET: str = "change-me-otp-link-secret"
    OTP_EXPIRATION_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5
    OTP_MAX_RESENDS: int = 3
    OTP_DELIVERY_MODE: str = "smtp"
    OTP_EXPOSE_CODE_IN_RESPONSE: bool = True

    # --- SMTP ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_SECURE: bool = True
    SMTP_USER: str = "huertoconnect@gmail.com"
    SMTP_APP_PASSWORD: str = "your-gmail-app-password"
    CONTACT_INBOX_EMAIL: str = "huertoconnec@gmail.com"

    # --- Password ---
    AUTH_PASSWORD_PEPPER: str = "change-me-pepper-secret"

    # --- Admin Seed ---
    ADMIN_EMAIL: str = "admin@huertoconnect.com"
    ADMIN_PASSWORD: str = "Admin123!"
    ADMIN_NOMBRE: str = "Administrador"
    ADMIN_APELLIDOS: str = "Sistema"

    # --- Service URLs (for gateway) ---
    AUTH_SERVICE_URL: str = "http://auth-service:8001"
    HUERTOS_SERVICE_URL: str = "http://huertos-service:8002"
    PLAGAS_SERVICE_URL: str = "http://plagas-service:8003"
    CHAT_SERVICE_URL: str = "http://chat-service:8004"
    REPORTES_SERVICE_URL: str = "http://reportes-service:8005"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
