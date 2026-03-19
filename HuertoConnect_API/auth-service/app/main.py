"""
Auth Service — FastAPI Application
Microservice for authentication: login, register, OTP, sessions.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth import router as auth_router
from app.routers.auth_otp import router as auth_otp_router
from app.routers.auth_google import router as auth_google_router
from app.routers.sessions import router as sessions_router
from app.core.scheduler import create_scheduler
from shared.config import settings
from shared.database import connect_mongodb, close_mongodb
from shared.auth.security import hash_password

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
    print("🔐 Auth Service starting...")
    db = await connect_mongodb()
    app.state.mongodb = db
    print(f"✅ Connected to MongoDB: {settings.MONGO_DB}")

    # Seed admin user if not exists
    admin = await db.usuarios.find_one({"email": settings.ADMIN_EMAIL.lower()})
    if not admin:
        pw_hash, pw_salt = hash_password(settings.ADMIN_PASSWORD)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await db.usuarios.insert_one({
            "nombre": settings.ADMIN_NOMBRE,
            "apellidos": settings.ADMIN_APELLIDOS,
            "email": settings.ADMIN_EMAIL.lower(),
            "password_hash": pw_hash,
            "password_salt": pw_salt,
            "rol": "Admin",
            "estado": "Activo",
            "email_verificado": True,
            "region_id": None,
            "ultima_actividad": now,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        })
        print(f"👤 Admin user seeded: {settings.ADMIN_EMAIL}")

    # ── Scheduler ────────────────────────────────────────────────────────
    scheduler = create_scheduler(db)
    scheduler.start()
    app.state.scheduler = scheduler
    print("📅 Cleanup scheduler started (OTP, resets, sessions).")

    print("  📖 Swagger UI: http://localhost:8001/docs")
    print("🔐 Auth Service ready on port 8001")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    print("📅 Scheduler stopped.")
    await close_mongodb()
    print("🔐 Auth Service stopped.")


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
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)                                     # Router original (shared/)
app.include_router(auth_otp_router)                                  # POST /auth/register, login, verify-otp, resend-otp
app.include_router(auth_google_router)                               # POST /auth/google, forgot-password, reset-password
app.include_router(sessions_router)                                  # GET /auth/session, logout, sesiones


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "auth-service"}
