"""Standalone Auth configuration, including aliases from the former Node mailer."""
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False, populate_by_name=True)
    ENVIRONMENT: str = "development"
    MONGO_URL: str = Field(default="mongodb://localhost:27017", validation_alias=AliasChoices("MONGO_URI", "MONGO_URL"))
    DB_NAME: str = Field(default="huerto_connect", validation_alias=AliasChoices("MONGO_DB", "DB_NAME"))
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = Field(default=8, ge=1, le=168, validation_alias=AliasChoices("JWT_EXPIRE_HOURS", "JWT_EXPIRATION_HOURS"))
    OTP_HASH_SECRET: str = Field(min_length=32)
    OTP_LINK_SECRET: str = ""
    OTP_EXPIRATION_MINUTES: int = Field(default=5, ge=1, le=15)
    OTP_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
    OTP_MAX_RESENDS: int = Field(default=3, ge=0, le=10)
    OTP_DELIVERY_MODE: str = "smtp"
    OTP_EXPOSE_CODE_IN_RESPONSE: bool = False
    SMTP_HOST: str = Field(default="smtp.gmail.com", validation_alias=AliasChoices("SMTP_HOST", "OTP_EMAIL_HOST", "MAIL_SERVER"))
    SMTP_PORT: int = Field(default=465, validation_alias=AliasChoices("SMTP_PORT", "OTP_EMAIL_PORT"))
    SMTP_SECURE: bool = Field(default=True, validation_alias=AliasChoices("SMTP_SECURE", "OTP_EMAIL_SECURE"))
    SMTP_USER: str = Field(default="", validation_alias=AliasChoices("SMTP_USER", "OTP_EMAIL_USER", "MAIL_USERNAME"))
    SMTP_APP_PASSWORD: str = Field(default="", validation_alias=AliasChoices("SMTP_APP_PASSWORD", "OTP_EMAIL_APP_PASSWORD", "MAIL_PASSWORD"))
    SMTP_TIMEOUT_SECONDS: float = Field(default=15, ge=1, le=60)
    MAIL_FROM: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_TIMEOUT_SECONDS: float = Field(default=10, ge=1, le=30)
    FRONTEND_URL: str = "http://localhost:4200"
    FRONTEND_ORIGIN: str = "http://localhost:4200"
    FRONTEND_LOGIN_PATH: str = "/auth/login"
    API_PUBLIC_URL: str = "http://localhost:8000"
    CORS_ORIGINS: str = ""
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_NOMBRE: str = "Administrador"
    ADMIN_APELLIDOS: str = "Sistema"

    @property
    def cors_origins(self):
        return [v.strip() for v in (self.CORS_ORIGINS or self.FRONTEND_ORIGIN).split(",") if v.strip()]

    @model_validator(mode="after")
    def validate_settings(self):
        self.SMTP_APP_PASSWORD = "".join(self.SMTP_APP_PASSWORD.split())
        if self.OTP_DELIVERY_MODE not in {"smtp", "console"}:
            raise ValueError("OTP_DELIVERY_MODE debe ser smtp o console")
        if "*" in self.cors_origins:
            raise ValueError("Configura orígenes CORS explícitos")
        if self.ENVIRONMENT == "production" and (self.OTP_EXPOSE_CODE_IN_RESPONSE or self.OTP_DELIVERY_MODE != "smtp"):
            raise ValueError("Producción requiere SMTP y códigos ocultos")
        return self

settings = Settings()
