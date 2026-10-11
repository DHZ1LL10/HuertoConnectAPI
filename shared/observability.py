"""Consistent health and sanitized request logging."""
import logging
from time import perf_counter
from bson.errors import InvalidId
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


def install_observability(app, service: str):
    from shared.low_data import install_low_data
    install_low_data(app)
    logger = logging.getLogger(service)

    @app.exception_handler(InvalidId)
    async def invalid_id(request, exc):
        return JSONResponse({"detail": "Identificador inválido"}, status_code=422)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("request_failed service=%s method=%s error=%s", service, request.method, type(exc).__name__)
            response = JSONResponse({"detail": "Error interno del servicio"}, status_code=500)
        route = request.scope.get("route")
        logger.info("service=%s endpoint=%s status=%s duration_ms=%.1f", service, getattr(route, "path", "unmatched"), response.status_code, (perf_counter()-start)*1000)
        return response

    @app.get("/health", tags=["Health"])
    async def health(request: Request):
        checks = {}
        try:
            if hasattr(app.state, "mongodb"):
                await app.state.mongodb.command("ping")
                checks["mongodb"] = True
            if hasattr(app.state, "engine"):
                async with app.state.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                checks["postgres"] = True
        except Exception:
            return JSONResponse({"status": "degraded", "service": service}, status_code=503)
        return {"status": "ok", "service": service, "dependencies": checks}
