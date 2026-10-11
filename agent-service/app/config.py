from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Huerto Connect Agent Pro"
    app_version: str = "3.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    # Seguridad entre el backend principal y este servicio.
    app_api_key: SecretStr = Field(validation_alias=AliasChoices("APP_API_KEY", "AGENT_API_KEY", "app_api_key"))

    # Ollama local o en una red privada.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:1b"
    ollama_timeout_seconds: float = Field(default=120.0, ge=5, le=600)
    ollama_health_timeout_seconds: float = Field(default=3, ge=0.1, le=10)
    max_concurrent_generations: int = Field(default=1, ge=1, le=8)
    queue_timeout_seconds: float = Field(default=2, ge=0.01, le=30)
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_history_characters: int = Field(default=2400, ge=100, le=32000)
    ollama_temperature: float = Field(default=0.25, ge=0, le=1.5)
    ollama_top_p: float = Field(default=0.9, ge=0.1, le=1)
    ollama_context_window: int = Field(default=2048, ge=1024, le=32768)
    ollama_max_output_tokens: int = Field(default=180, ge=64, le=2048)
    ollama_keep_alive: str = "30m"

    # Conversaciones y validación.
    max_message_length: int = Field(default=2000, ge=100, le=10000)
    max_history_messages: int = Field(default=6, ge=2, le=50)
    max_response_words: int = Field(default=180, ge=60, le=500)
    max_user_id_length: int = Field(default=128, ge=16, le=255)

    # Rate limit en memoria. Para varias réplicas usar Redis/API Gateway.
    rate_limit_requests: int = Field(default=20, ge=1, le=1000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_max_users: int = Field(default=10000, ge=1, le=100000)
    allowed_hosts: str = "localhost,127.0.0.1,testserver,agent-service,agent"

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
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("OLLAMA_BASE_URL debe ser una URL HTTP(S) sin credenciales ni parámetros")
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
    def hosts(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]



@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    return settings
