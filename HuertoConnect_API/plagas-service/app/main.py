"""
Plagas Service — FastAPI Application
Microservice for plagas, alertas, AI models, predictions, dashboard.
Uses PostgreSQL via SQLAlchemy async + MongoDB for auth session validation.
"""

from contextlib import asynccontextmanager

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
from shared.config import settings
from shared.database import (
    connect_mongodb,
    close_mongodb,
    get_postgres_engine,
    get_session_factory,
    init_postgres_tables,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("🐛 Plagas Service starting...")

    # MongoDB for auth session validation
    db = await connect_mongodb()
    app.state.mongodb = db
    print("  ✅ Connected to MongoDB (auth sessions)")

    # PostgreSQL for plagas data
    engine = get_postgres_engine()
    app.state.engine = engine
    app.state.session_factory = get_session_factory(engine)
    await init_postgres_tables(engine)
    print("  ✅ Connected to PostgreSQL (plagas data)")

    port = 8003
    print(f"  📖 Swagger UI: http://localhost:{port}/docs")
    print(f"🐛 Plagas Service ready on port {port}")

    yield

    await engine.dispose()
    await close_mongodb()
    print("🐛 Plagas Service stopped.")


app = FastAPI(
    title="Huerto Connect — Plagas Service",
    description="Microservicio de plagas, alertas, IA: detecciones, modelos, predicciones, dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plagas_router)
app.include_router(alertas_router)
app.include_router(dashboard_router)
app.include_router(modelos_router)
app.include_router(predicciones_router)
app.include_router(datasets_router)
app.include_router(recomendaciones_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "plagas-service"}
