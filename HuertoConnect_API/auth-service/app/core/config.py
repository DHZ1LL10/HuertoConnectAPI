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

    # --- Email (fastapi-mail / SMTP) ---
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_SERVER: str = "smtp.gmail.com"

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""

    # --- Cloudinary ---
    CLOUDINARY_URL: str = ""

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:4200"
    FRONTEND_ORIGIN: str = "http://localhost:4200"


settings = Settings()
