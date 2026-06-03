"""auth_service.routers — Routers FastAPI del Auth Service."""

from app.routers.auth_otp import router as auth_otp_router
from app.routers.auth_google import router as auth_google_router
from app.routers.sessions import router as sessions_router

__all__ = [
    "auth_otp_router",
    "auth_google_router",
    "sessions_router",
]
