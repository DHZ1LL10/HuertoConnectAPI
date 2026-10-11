"""
Plagas Service — FastAPI Application
Microservice for plagas, alertas, AI models, predictions, dashboard.
Uses PostgreSQL via SQLAlchemy async + MongoDB for auth session validation.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.routes import (
    alertas_router,
    dashboard_router,
    datasets_router,
    modelos_router,
    plagas_router,
    predicciones_router,
    recomendaciones_router,
)
from app.routes.ia_detectar import router as ia_detectar_router
from app.routes.ai import router as ai_router
from app.ai.model_manager import ModelManager
from starlette.concurrency import run_in_threadpool
from shared.config import settings
from shared.database import (
    connect_mongodb,
    close_mongodb,
    get_postgres_engine,
    get_session_factory,
    init_postgres_tables,
)


logger = logging.getLogger("plagas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = None
    app.state.models = ModelManager()
    try:
        app.state.mongodb = await connect_mongodb()
        await app.state.mongodb.diagnosticos.create_index([("usuario_id", 1), ("huerto_id", 1), ("fecha", -1)])
        engine = get_postgres_engine()
        app.state.engine = engine
        app.state.session_factory = get_session_factory(engine)
        await init_postgres_tables(engine)
        await run_in_threadpool(app.state.models.load)
        logger.info("plagas_started models=%s", app.state.models.health())
        yield
    finally:
        if engine is not None:
            await engine.dispose()
        await close_mongodb()
        app.state.models.models.clear()
        logger.info("plagas_stopped")


app = FastAPI(
    title="Huerto Connect — Plagas Service",
    description="Microservicio de plagas, alertas, IA: detecciones, modelos, predicciones, dashboard",
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"tryItOutEnabled": True, "persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plagas_router, include_in_schema=False)
app.include_router(alertas_router)
app.include_router(dashboard_router)
app.include_router(modelos_router, include_in_schema=False)
app.include_router(predicciones_router, include_in_schema=False)
app.include_router(datasets_router)
app.include_router(recomendaciones_router, include_in_schema=False)
app.include_router(ia_detectar_router)
app.include_router(ai_router)
from shared.observability import install_observability
install_observability(app, "plagas")
from shared.openapi_uploads import enable_upload_controls
enable_upload_controls(app)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "plagas-service"}

@app.get("/health/live", tags=["Health"])
async def live():
    return {"status": "ok", "service": "plagas-service"}


@app.get("/health/ready", tags=["Health"])
async def ready(request: Request):
    checks = {"mongodb": False, "postgres": False}
    try:
        async with asyncio.timeout(5):
            await request.app.state.mongodb.command("ping")
            checks["mongodb"] = True
            async with request.app.state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            checks["postgres"] = True
    except Exception:
        pass
    models = request.app.state.models.health() if hasattr(request.app.state, "models") else {}
    ok = all(checks.values()) and bool(models) and all(m["loaded"] for m in models.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "dependencies": checks, "models": models}, status_code=200 if ok else 503)


@app.exception_handler(IntegrityError)
async def invalid_relation(request, exc):
    return JSONResponse({"detail": "Registro duplicado o referencia inexistente"}, status_code=409)


@app.middleware("http")
async def bounded_body(request, call_next):
    # Bound multipart bodies before Starlette spools uploads to disk.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > settings.AI_MAX_IMAGE_BYTES + 65536:
            return JSONResponse({"detail": "Solicitud demasiado grande"}, status_code=413)
        body.extend(chunk)
    request._body = bytes(body)
    return await call_next(request)
