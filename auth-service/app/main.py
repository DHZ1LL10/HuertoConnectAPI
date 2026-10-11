"""
Auth Service — FastAPI Application
Microservice for authentication: login, register, OTP, sessions.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from app.core.rate_limit import enforce_auth_rate_limit
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth_otp import router as auth_otp_router
from app.routers.auth_google import router as auth_google_router
from app.routers.sessions import router as sessions_router
from app.core.config import settings
from app.core.database import connect_db, close_db, get_db
from app.core.scheduler import create_scheduler
from app.core.security import hash_password

# Logging básico para mostrar los mensajes del scheduler en consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ──────────────────────────────────────────────────────────
    print("Auth Service starting...")
    await connect_db()
    db = get_db()
    app.state.mongodb = db
    await db.usuarios.create_index("email", unique=True)
    await db.usuarios.create_index("google_id", unique=True, partialFilterExpression={"google_id": {"$type": "string"}})
    await db.sesiones.create_index("token_hash", unique=True)
    await db.sesiones.create_index("jti", sparse=True, unique=True)
    await db.otp_challenges.create_index("expires_at", expireAfterSeconds=0)
    await db.auth_rate_limits.create_index("expires_at", expireAfterSeconds=0)
    print(f"Connected to MongoDB: {settings.DB_NAME}")

    # Optional initial admin; never overwrite existing credentials.
    admin = await db.usuarios.find_one({"email": settings.ADMIN_EMAIL.lower()})
    if not admin and settings.ADMIN_PASSWORD and settings.ADMIN_EMAIL:
        pw_hash = hash_password(settings.ADMIN_PASSWORD)
        now = datetime.now(timezone.utc)
        await db.usuarios.insert_one({
            "nombre": settings.ADMIN_NOMBRE,
            "apellidos": settings.ADMIN_APELLIDOS,
            "email": settings.ADMIN_EMAIL.lower(),
            "password_hash": pw_hash,
            "role": "admin",
            "auth_provider": "email",
            "estado": "Activo",
            "email_verificado": True,
            "google_id": None,
            "profile_picture": None,
            "region_id": None,
            "ultima_actividad": now,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        })
        print("Admin user seeded")

    # ── Scheduler ────────────────────────────────────────────────────────
    scheduler = create_scheduler(db)
    scheduler.start()
    app.state.scheduler = scheduler
    print("Cleanup scheduler started (OTP, resets, sessions).")

    print("Swagger UI: http://localhost:8001/docs")
    print("Auth Service ready on port 8001")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    print("Scheduler stopped.")
    await close_db()
    print("Auth Service stopped.")


app = FastAPI(
    title="Huerto Connect — Auth Service",
    description="Microservicio de autenticación: login, registro, OTP, sesiones",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — origins explícitas (wildcard no compatible con allow_credentials=True)
_ALLOWED_ORIGINS = list({
    "http://localhost:4200",        # Angular dev
    "http://localhost:3000",        # React/Next dev (por si se usa)
    settings.FRONTEND_ORIGIN,      # Producción (del .env)
    settings.FRONTEND_URL,
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import APIRouter

api_router = APIRouter(prefix="/api", dependencies=[Depends(enforce_auth_rate_limit)])
api_router.include_router(auth_otp_router)       # POST /api/auth/register, login, send-otp, verify-otp, resend-otp
api_router.include_router(auth_google_router)    # POST /api/auth/google, forgot-password, reset-password
api_router.include_router(sessions_router)       # GET /api/auth/session, /me, logout, sesiones

# Routes — consolidados bajo /api/auth
app.include_router(api_router)
from shared.observability import install_observability
install_observability(app, "auth")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "auth-service"}


@app.get("/health/ready")
async def ready():
    from shared.readiness import dependency_readiness
    return await dependency_readiness(app.state.mongodb)
