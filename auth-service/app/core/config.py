"""
Auth Service — Configuración centralizada mediante pydantic-settings.

Lee variables de entorno (o del archivo .env) y las expone
como atributos tipados a través del objeto ``settings``.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de configuración del Auth Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",         # ignora variables del .env que no están aquí
    )

    # --- MongoDB ---
    MONGO_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "huerto_connect"

    # --- JWT ---
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    # --- Email (SMTP) ---
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_SERVER: str = "smtp.gmail.com"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_SECURE: bool = True
    SMTP_USER: str = ""
    SMTP_APP_PASSWORD: str = ""

    # --- OTP ---
    OTP_DELIVERY_MODE: str = "console"
    OTP_EXPOSE_CODE_IN_RESPONSE: bool = True
    OTP_EXPIRATION_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5
    OTP_MAX_RESENDS: int = 3
    OTP_HASH_SECRET: str = "change-me-otp-secret"
    OTP_LINK_SECRET: str = "change-me-otp-link-secret"

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:4200"
    FRONTEND_ORIGIN: str = "http://localhost:4200"
    FRONTEND_LOGIN_PATH: str = "/auth/login"

    # --- API ---
    API_PUBLIC_URL: str = "http://localhost:8001"

    # --- Admin Seed ---
    ADMIN_EMAIL: str = "admin@huertoconnect.com"
    ADMIN_PASSWORD: str = "Admin123!"
    ADMIN_NOMBRE: str = "Administrador"
    ADMIN_APELLIDOS: str = "Sistema"

    # --- Cloudinary ---
    CLOUDINARY_URL: str = ""


settings = Settings()
