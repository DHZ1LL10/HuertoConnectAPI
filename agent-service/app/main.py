from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, get_settings
from app.db import Database
from app.locks import ConversationLockManager
from app.providers.ollama import OllamaProvider, OllamaTimeoutError, OllamaUnavailableError
from app.rate_limit import InMemoryRateLimiter
from app.repository import ConversationNotFoundError, ConversationRepository
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationMessagesResponse,
    DeleteConversationResponse,
    HealthResponse,
    MessageResponse,
)
from app.service import ChatService

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:@-]+$")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = logging.getLogger("huerto-connect-agent")


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(settings: Settings | None = None, provider: OllamaProvider | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings)
        await database.create_schema()
        actual_provider = provider or OllamaProvider(settings)
        repository = ConversationRepository(database.session_factory)

        app.state.settings = settings
        app.state.database = database
        app.state.provider = actual_provider
        app.state.repository = repository
        app.state.chat_service = ChatService(
            settings,
            actual_provider,
            repository,
            ConversationLockManager(),
        )
        app.state.rate_limiter = InMemoryRateLimiter(
            settings.rate_limit_requests,
            settings.rate_limit_window_seconds,
        )
        yield
        await actual_provider.close()
        await database.close()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Agente seguro para Huerto Connect con Ollama, historial en servidor "
            "y aislamiento de conversaciones por usuario."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "X-User-ID"],
    )

    async def require_api_key(
        request: Request,
        supplied_key: str | None = Depends(api_key_header),
    ) -> None:
        configured = request.app.state.settings.app_api_key.get_secret_value()
        if not supplied_key or not secrets.compare_digest(supplied_key, configured):
            raise HTTPException(status_code=401, detail="API key inválida")

    async def require_user_id(
        request: Request,
        x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    ) -> str:
        if not x_user_id:
            raise HTTPException(status_code=401, detail="Falta X-User-ID")
        user_id = x_user_id.strip()
        max_length = request.app.state.settings.max_user_id_length
        if not user_id or len(user_id) > max_length or not USER_ID_PATTERN.fullmatch(user_id):
            raise HTTPException(status_code=400, detail="X-User-ID inválido")
        return user_id

    def get_client_ip(request: Request) -> str:
        settings_local = request.app.state.settings
        if settings_local.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def enforce_rate_limit(
        request: Request,
        user_id: str = Depends(require_user_id),
    ) -> None:
        key = f"{user_id}:{get_client_ip(request)}"
        allowed = await request.app.state.rate_limiter.allow(key)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiadas solicitudes. Intenta nuevamente más tarde.",
            )

    @app.exception_handler(ConversationNotFoundError)
    async def conversation_not_found(_request: Request, _exc: ConversationNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Conversación no encontrada"})

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            model=settings.ollama_model,
        )

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready(request: Request) -> HealthResponse:
        database_ok = await request.app.state.database.health()
        ollama_ok = await request.app.state.provider.health()
        if not (database_ok and ollama_ok):
            raise HTTPException(
                status_code=503,
                detail={"database": database_ok, "ollama": ollama_ok},
            )
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            model=settings.ollama_model,
            database=True,
            ollama=True,
        )

    @app.post(
        "/v1/chat",
        response_model=ChatResponse,
        dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
        tags=["chat"],
    )
    async def chat(
        payload: ChatRequest,
        request: Request,
        user_id: str = Depends(require_user_id),
    ):
        request_id = str(uuid.uuid4())
        user_fingerprint = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
        try:
            result = await request.app.state.chat_service.chat(
                user_id=user_id,
                message=payload.message,
                conversation_id=payload.conversation_id,
            )
            logger.info(
                "chat_completed request_id=%s user=%s conversation=%s status=%s reason=%s",
                request_id,
                user_fingerprint,
                result.conversation_id,
                result.status,
                result.safety_reason,
            )
            return ChatResponse(
                answer=result.answer,
                conversation_id=result.conversation_id,
                status=result.status,
                safety_reason=result.safety_reason,
                request_id=request_id,
                model=result.model,
            )
        except OllamaTimeoutError:
            response = ChatResponse(
                answer="El modelo tardó demasiado en responder. Intenta nuevamente en unos momentos.",
                conversation_id=payload.conversation_id,
                status="error",
                safety_reason="provider_timeout",
                request_id=request_id,
                model=settings.ollama_model,
            )
            return JSONResponse(status_code=504, content=response.model_dump())
        except OllamaUnavailableError as exc:
            logger.warning("ollama_unavailable request_id=%s error=%s", request_id, str(exc))
            response = ChatResponse(
                answer=(
                    "El asistente no está disponible temporalmente. No apliques productos nuevos "
                    "mientras no se confirme el problema del cultivo."
                ),
                conversation_id=payload.conversation_id,
                status="error",
                safety_reason="provider_unavailable",
                request_id=request_id,
                model=settings.ollama_model,
            )
            return JSONResponse(status_code=503, content=response.model_dump())

    @app.get(
        "/v1/conversations/{conversation_id}/messages",
        response_model=ConversationMessagesResponse,
        dependencies=[Depends(require_api_key)],
        tags=["conversations"],
    )
    async def conversation_messages(
        conversation_id: str,
        request: Request,
        user_id: str = Depends(require_user_id),
    ) -> ConversationMessagesResponse:
        messages = await request.app.state.repository.list_messages(
            conversation_id,
            user_id,
            limit=100,
        )
        return ConversationMessagesResponse(
            conversation_id=conversation_id,
            messages=[
                MessageResponse(role=item.role, content=item.content, created_at=item.created_at)
                for item in messages
            ],
        )

    @app.delete(
        "/v1/conversations/{conversation_id}",
        response_model=DeleteConversationResponse,
        dependencies=[Depends(require_api_key)],
        tags=["conversations"],
    )
    async def delete_conversation(
        conversation_id: str,
        request: Request,
        user_id: str = Depends(require_user_id),
    ) -> DeleteConversationResponse:
        deleted = await request.app.state.repository.delete_owned(conversation_id, user_id)
        return DeleteConversationResponse(deleted=deleted, conversation_id=conversation_id)

    return app


app = create_app()
