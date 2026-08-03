from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ChatStatus = Literal["answered", "blocked", "redirected", "error"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El mensaje no puede estar vacío")
        return value


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str | None = None
    status: ChatStatus
    safety_reason: str | None = None
    request_id: str
    model: str | None = None


class MessageResponse(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    conversation_id: str
    messages: list[MessageResponse]


class DeleteConversationResponse(BaseModel):
    deleted: bool
    conversation_id: str


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    service: str
    version: str
    model: str | None = None
    database: bool | None = None
    ollama: bool | None = None
