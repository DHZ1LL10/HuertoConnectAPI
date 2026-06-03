"""
Huertos Service — FastAPI Application
Microservice for huertos, regiones, cultivos, contacto, usuarios admin.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.regiones import router as regiones_router
from app.routes.huertos import router as huertos_router
from app.routes.cultivos import router as cultivos_router
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
    """Startup and shutdown events."""
    print("🌿 Huertos Service starting...")
    db = await connect_mongodb()
    app.state.mongodb = db
    # Notifications are read by user and ordered by date in the panel.
    await db.notificaciones_usuario.create_index([("usuario_id", 1), ("fecha", -1)])
    await db.notificaciones_usuario.create_index([("usuario_id", 1), ("leida", 1)])
    print(f"  ✅ Connected to MongoDB: {settings.MONGO_DB}")
    print("  📖 Swagger UI: http://localhost:8002/docs")
    print("🌿 Huertos Service ready on port 8002")
    yield
    await close_mongodb()
    print("🌿 Huertos Service stopped.")


app = FastAPI(
    title="Huerto Connect — Huertos Service",
    description="Microservicio agrícola: huertos, regiones, cultivos, plantíos",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(regiones_router)
app.include_router(huertos_router)
app.include_router(cultivos_router)
app.include_router(contacto_router)
app.include_router(usuarios_router)
app.include_router(notificaciones_router)
app.include_router(dataset_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "huertos-service"}
