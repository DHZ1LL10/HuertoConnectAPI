"""Internal stateless Agent. Public conversations remain in Chat/MongoDB."""
import logging
import re
import secrets
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.config import Settings, get_settings
from app.providers.ollama import OllamaProvider, OllamaTimeoutError, OllamaUnavailableError
from app.rate_limit import InMemoryRateLimiter
from app.schemas import GenerateRequest, GenerateResponse, HealthResponse
from app.service import GenerationService, GenerationBusyError

logger = logging.getLogger("huerto.agent")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def create_app(settings: Settings | None = None, provider=None):
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
        app.state.provider = provider or OllamaProvider(settings)
        if provider is None:
            await app.state.provider.warm()
        app.state.generator = GenerationService(settings, app.state.provider)
        app.state.limiter = InMemoryRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds, settings.rate_limit_max_users)
        try:
            yield
        finally:
            await app.state.provider.close()

    app = FastAPI(title=settings.app_name, version=settings.app_version,
                  description="Servicio interno de generación con Ollama. El historial pertenece a Chat.",
                  lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = str(uuid4())
        start = perf_counter()
        # Buffer a bounded request, including chunked clients, before JSON parsing.
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > settings.max_request_bytes:
                    return JSONResponse({"detail": "Solicitud demasiado grande", "request_id": request.state.request_id}, status_code=413)
            request._body = bytes(body)
            response = await call_next(request)
        except Exception as exc:
            logger.error("request_failed request_id=%s error=%s", request.state.request_id, type(exc).__name__)
            response = JSONResponse({"detail": "Error interno del agente", "request_id": request.state.request_id}, status_code=500)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info("request_id=%s method=%s endpoint=%s status=%s duration_ms=%.1f",
                    request.state.request_id, request.method, getattr(request.scope.get("route"), "path", "unmatched"),
                    response.status_code, (perf_counter()-start)*1000)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # FastAPI defaults echo the invalid input, which can contain private history.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": errors, "request_id": request.state.request_id}, status_code=422)

    async def authorize(supplied: str | None = Depends(key_header)):
        if not supplied or not secrets.compare_digest(supplied, settings.app_api_key.get_secret_value()):
            raise HTTPException(401, "API key inválida")

    async def user_identity(x_user_id: str | None = Header(None)):
        if not x_user_id:
            raise HTTPException(401, "Falta X-User-ID")
        if len(x_user_id) > settings.max_user_id_length or not re.fullmatch(r"[A-Za-z0-9._:@-]+", x_user_id):
            raise HTTPException(422, "X-User-ID inválido")
        return x_user_id

    def health_payload(available=None):
        return {"status": "unavailable" if available is False else "ok", "service": settings.app_name,
                "version": settings.app_version, "model": settings.ollama_model, "ollama": available}

    @app.get("/api/health", response_model=HealthResponse, tags=["Health"])
    @app.get("/health/live", response_model=HealthResponse, tags=["Health"])
    async def live():
        return health_payload()

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    @app.get("/health/ready", response_model=HealthResponse, tags=["Health"])
    async def ready(request: Request):
        available = await request.app.state.provider.health()
        return JSONResponse(health_payload(available), status_code=200 if available else 503)

    @app.post("/v1/generate", response_model=GenerateResponse, dependencies=[Depends(authorize)],
              responses={401: {"description": "Credencial interna inválida"}, 413: {"description": "Cuerpo demasiado grande"},
                         422: {"description": "Mensaje inválido"}, 429: {"description": "Límite o saturación"},
                         503: {"description": "Ollama no disponible"}, 504: {"description": "Tiempo agotado"}},
              tags=["Generación"])
    async def generate(body: GenerateRequest, request: Request, user: str = Depends(user_identity)):
        if len(body.message) > settings.max_message_length:
            raise HTTPException(422, f"El mensaje admite hasta {settings.max_message_length} caracteres")
        if not await request.app.state.limiter.allow(user):
            raise HTTPException(429, "Demasiadas solicitudes", headers={"Retry-After": str(settings.rate_limit_window_seconds)})
        try:
            result = await request.app.state.generator.generate(body.message, body.history)
            return GenerateResponse(**result, request_id=request.state.request_id)
        except GenerationBusyError:
            raise HTTPException(429, "El agente está ocupado. Intenta de nuevo.", headers={"Retry-After": "2"})
        except OllamaTimeoutError:
            raise HTTPException(504, "Ollama excedió el tiempo de respuesta")
        except OllamaUnavailableError:
            raise HTTPException(503, "Ollama no disponible")

    @app.post("/v1/chat", deprecated=True, dependencies=[Depends(authorize)], tags=["Compatibilidad"])
    @app.get("/v1/conversations/{conversation_id}/messages", deprecated=True, dependencies=[Depends(authorize)], tags=["Compatibilidad"])
    @app.delete("/v1/conversations/{conversation_id}", deprecated=True, dependencies=[Depends(authorize)], tags=["Compatibilidad"])
    async def legacy():
        raise HTTPException(410, "El historial ahora pertenece a Chat. Utiliza /api/agent/v1/chat y /api/agent/v1/conversations desde el Gateway.")

    return app


app = create_app()
