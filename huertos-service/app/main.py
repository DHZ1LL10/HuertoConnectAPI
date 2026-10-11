"""
Huertos Service — FastAPI Application
Microservice for huertos, regiones, cultivos, contacto, usuarios admin.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.regiones import router as regiones_router
from app.routes.huertos import router as huertos_router
from app.routes.cultivos import router as cultivos_router
from app.routes.comunidad import router as comunidad_router
from app.routes.extras import (
    contacto_router,
    usuarios_router,
    notificaciones_router,
    dataset_router,
)
from shared.config import settings
from shared.database import connect_mongodb, close_mongodb


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db = await connect_mongodb()
        app.state.mongodb = db
        from shared.regions import seed_regions
        await seed_regions(db)
        from app.services.comunidad import init_indexes
        await init_indexes(db)
        await db.huertos.create_index([("usuario_id", 1), ("deleted_at", 1)])
        await db.huerto_cultivos.create_index("huerto_id")
        await db.plantios.create_index("huerto_cultivo_id")
        await db.dataset_imagenes.create_index([("usuario_id", 1), ("huerto_id", 1)])
        await db.notificaciones_usuario.create_index([("usuario_id", 1), ("fecha", -1)])
        await db.notificaciones_usuario.create_index([("usuario_id", 1), ("leida", 1)])
        yield
    finally:
        await close_mongodb()


app = FastAPI(
    title="Huerto Connect — Huertos Service",
    description="Microservicio agrícola: huertos, regiones, cultivos, plantíos y comunidad agricultora",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(regiones_router)
app.include_router(huertos_router)
app.include_router(cultivos_router)
app.include_router(comunidad_router)
app.include_router(contacto_router)
app.include_router(usuarios_router)
app.include_router(notificaciones_router)
app.include_router(dataset_router)
from shared.observability import install_observability
install_observability(app, "huertos")
from shared.openapi_uploads import enable_upload_controls
enable_upload_controls(app)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "huertos-service"}

@app.get("/health/live", tags=["Health"])
async def live():
    return {"status": "ok", "service": "huertos-service"}


@app.get("/health/ready", tags=["Health"])
async def ready():
    try:
        async with asyncio.timeout(5):
            await app.state.mongodb.command("ping")
    except Exception:
        return JSONResponse({"status": "unavailable", "mongodb": False}, status_code=503)
    return {"status": "ok", "mongodb": True}


@app.exception_handler(DuplicateKeyError)
async def duplicate_key(request, exc):
    return JSONResponse({"detail": "Ya existe un registro con esos datos"}, status_code=409)


@app.middleware("http")
async def bounded_body(request, call_next):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 5 * 1024 * 1024 + 65536:
            return JSONResponse({"detail": "Solicitud demasiado grande"}, status_code=413)
        body.extend(chunk)
    request._body = bytes(body)
    return await call_next(request)
