"""The internal Agent contract never accepts conversation IDs or system messages."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

ChatStatus = Literal["answered", "blocked", "redirected", "error"]


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El contenido no puede estar vacío")
        return value


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=10000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=50)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El mensaje no puede estar vacío")
        return value


class GenerateResponse(BaseModel):
    answer: str
    status: ChatStatus
    safety_reason: str | None = None
    request_id: str
    model: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str
    version: str
    model: str
    ollama: bool | None = None
