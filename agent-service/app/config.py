from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Huerto Connect Agent Pro"
    app_version: str = "2.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Seguridad entre el backend principal y este servicio.
    app_api_key: SecretStr = SecretStr(
        "development-only-change-this-api-key-1234567890"
    )

    # Base de datos. Para producción se recomienda PostgreSQL.
    database_url: str = "sqlite:///./data/huerto_connect.db"
    database_echo: bool = False

    # Ollama local o en una red privada.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = Field(default=120.0, ge=5, le=600)
    ollama_temperature: float = Field(default=0.25, ge=0, le=1.5)
    ollama_top_p: float = Field(default=0.9, ge=0.1, le=1)
    ollama_context_window: int = Field(default=4096, ge=1024, le=32768)
    ollama_max_output_tokens: int = Field(default=320, ge=64, le=2048)
    ollama_keep_alive: str = "10m"

    # Conversaciones y validación.
    max_message_length: int = Field(default=2000, ge=100, le=10000)
    max_history_messages: int = Field(default=12, ge=2, le=50)
    max_response_words: int = Field(default=180, ge=60, le=500)
    max_user_id_length: int = Field(default=128, ge=16, le=255)

    # Rate limit en memoria. Para varias réplicas usar Redis/API Gateway.
    rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    trust_proxy_headers: bool = False

    allowed_origins: str = ""
    allowed_hosts: str = "localhost,127.0.0.1,testserver"

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"development", "testing", "production"}:
            raise ValueError("ENVIRONMENT debe ser development, testing o production")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        api_key = self.app_api_key.get_secret_value()
        if len(api_key) < 32:
            raise ValueError("APP_API_KEY debe tener al menos 32 caracteres")
        placeholders = ("development-only", "cambia_esta", "change-this", "tu_app_api_key")
        if self.environment == "production" and any(item in api_key.lower() for item in placeholders):
            raise ValueError("Debes cambiar APP_API_KEY antes de producción")
        return self

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]

    @property
    def hosts(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def ensure_local_paths(self) -> None:
        if self.database_url.startswith("sqlite"):
            database_path = self.database_url.split("///", 1)[-1]
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_local_paths()
    return settings
