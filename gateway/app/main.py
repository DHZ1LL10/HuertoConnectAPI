"""
API Gateway — Reverse proxy to all Huerto Connect microservices.
Single entry point for the frontend.
Unified Swagger UI at /docs with all services' endpoints.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse, JSONResponse

from shared.config import settings


# Service URL mapping
SERVICE_MAP = {
    "/api/auth": settings.AUTH_SERVICE_URL,
    "/api/usuarios": settings.HUERTOS_SERVICE_URL,
    "/api/huertos": settings.HUERTOS_SERVICE_URL,
    "/api/regiones": settings.HUERTOS_SERVICE_URL,
    "/api/cultivos": settings.HUERTOS_SERVICE_URL,
    "/api/public": settings.HUERTOS_SERVICE_URL,
    "/api/notificaciones": settings.HUERTOS_SERVICE_URL,
    "/api/datasets/imagenes": settings.HUERTOS_SERVICE_URL,
    "/api/plagas": settings.PLAGAS_SERVICE_URL,
    "/api/alertas": settings.PLAGAS_SERVICE_URL,
    "/api/dashboard": settings.PLAGAS_SERVICE_URL,
    "/api/modelos": settings.PLAGAS_SERVICE_URL,
    "/api/predicciones": settings.PLAGAS_SERVICE_URL,
    "/api/datasets": settings.PLAGAS_SERVICE_URL,
    "/api/recomendaciones": settings.PLAGAS_SERVICE_URL,
    "/api/chatbot": settings.CHAT_SERVICE_URL,
    "/api/reportes": settings.REPORTES_SERVICE_URL,
    "/api/auditoria": settings.REPORTES_SERVICE_URL,
}

# Services for documentation aggregation
SERVICES = {
    "auth": {"url": settings.AUTH_SERVICE_URL, "label": "Auth Service"},
    "huertos": {"url": settings.HUERTOS_SERVICE_URL, "label": "Huertos Service"},
    "plagas": {"url": settings.PLAGAS_SERVICE_URL, "label": "Plagas/IA Service"},
    "chat": {"url": settings.CHAT_SERVICE_URL, "label": "Chat Service"},
    "reportes": {"url": settings.REPORTES_SERVICE_URL, "label": "Reportes Service"},
}

SWAGGER_UI_PARAMS = {
    "persistAuthorization": True,
    "displayRequestDuration": True,
    "filter": True,
    "deepLinking": True,
    "tryItOutEnabled": True,
    "docExpansion": "list",
    "defaultModelsExpandDepth": -1,
    "operationsSorter": "alpha",
    "tagsSorter": "alpha",
}

_http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown for HTTP client."""
    global _http_client
    print("🚀 API Gateway starting...")
    _http_client = httpx.AsyncClient(timeout=30.0)
    print(f"✅ Gateway ready on port {settings.API_PORT}")
    print(f"📖 Swagger UI: http://localhost:{settings.API_PORT}/docs")
    print(f"📖 ReDoc:      http://localhost:{settings.API_PORT}/redoc")
    yield
    await _http_client.aclose()
    _http_client = None
    print("🚀 API Gateway stopped.")


# Disable default docs, we provide our own
app = FastAPI(
    title="Huerto Connect — API Gateway",
    description="Punto de entrada único para todos los microservicios de Huerto Connect",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:4200", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _find_service_url(path: str) -> str | None:
    """Find the service URL for a given path by matching the longest prefix."""
    for prefix in sorted(SERVICE_MAP.keys(), key=len, reverse=True):
        if path.startswith(prefix):
            return SERVICE_MAP[prefix]
    return None


# ===================== UNIFIED OPENAPI =====================

@app.get("/openapi.json", include_in_schema=False)
async def unified_openapi():
    """Aggregate OpenAPI specs from all services into one."""
    merged = {
        "openapi": "3.1.0",
        "info": {
            "title": "Huerto Connect — API Completa",
            "description": (
                "Documentación unificada de todos los microservicios.\n\n"
                "**Servicios:**\n"
                "- Auth (login, registro, OTP, sesiones)\n"
                "- Huertos (regiones, huertos, cultivos, usuarios, notificaciones)\n"
                "- Plagas/IA (detecciones, alertas, modelos IA, predicciones, dashboard)\n"
                "- Chat (conversaciones, mensajes, métricas)\n"
                "- Reportes (reportes, auditoría)\n\n"
                "**Autenticación:** Usa `Bearer <JWT_TOKEN>` en el header Authorization.\n\n"
                "**Roles:** `Admin`, `Usuario`, `Tecnico`"
            ),
            "version": "1.0.0",
        },
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {},
        },
    }

    for name, svc in SERVICES.items():
        try:
            resp = await _http_client.get(f"{svc['url']}/openapi.json", timeout=5.0)
            if resp.status_code == 200:
                spec = resp.json()

                # Merge paths
                for path, methods in spec.get("paths", {}).items():
                    # Tag all operations with service name
                    for method, operation in methods.items():
                        if isinstance(operation, dict):
                            tags = operation.get("tags", [])
                            # Prefix tags with service label for grouping
                            operation["tags"] = [f"{svc['label']} — {t}" for t in tags] if tags else [svc["label"]]
                    merged["paths"][path] = methods

                # Merge schemas (prefix to avoid collisions)
                for schema_name, schema_def in spec.get("components", {}).get("schemas", {}).items():
                    # Use service prefix if there's a collision
                    key = schema_name
                    if key in merged["components"]["schemas"]:
                        key = f"{name}_{schema_name}"
                    merged["components"]["schemas"][key] = schema_def

                # Merge security schemes so Swagger "Authorize" works in unified docs
                for scheme_name, scheme_def in spec.get("components", {}).get("securitySchemes", {}).items():
                    existing = merged["components"]["securitySchemes"].get(scheme_name)
                    if existing is None:
                        merged["components"]["securitySchemes"][scheme_name] = scheme_def
                    elif existing != scheme_def:
                        merged["components"]["securitySchemes"][f"{name}_{scheme_name}"] = scheme_def

        except Exception as e:
            print(f"[DOCS] Could not fetch spec from {name}: {e}")

    # Add gateway's own health endpoint
    merged["paths"]["/api/health"] = {
        "get": {
            "tags": ["Gateway"],
            "summary": "Health check de todos los servicios",
            "operationId": "gateway_health",
            "responses": {
                "200": {
                    "description": "Status de todos los servicios",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                }
            },
        }
    }

    return JSONResponse(content=merged)


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    """Unified Swagger UI."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Huerto Connect — API Docs",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_ui_parameters=SWAGGER_UI_PARAMS,
    )


@app.get("/redoc", include_in_schema=False)
async def redoc():
    """Unified ReDoc."""
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="Huerto Connect — API Docs",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


# ===================== DOCS INDEX =====================

@app.get("/", include_in_schema=False)
async def docs_index():
    """Landing page with links to all documentation."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🌿 Huerto Connect API</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #1b4332, #2d6a4f); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .container { background: white; border-radius: 16px; padding: 48px; max-width: 600px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
            h1 { color: #1b4332; font-size: 28px; margin-bottom: 8px; }
            p.sub { color: #666; margin-bottom: 32px; }
            .links { display: flex; flex-direction: column; gap: 12px; }
            a.btn { display: flex; align-items: center; gap: 12px; padding: 16px 20px; border-radius: 10px; text-decoration: none; color: white; font-weight: 600; font-size: 16px; transition: transform 0.2s, box-shadow 0.2s; }
            a.btn:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); }
            .swagger { background: linear-gradient(135deg, #2d6a4f, #40916c); }
            .redoc { background: linear-gradient(135deg, #1b4332, #2d6a4f); }
            .health { background: linear-gradient(135deg, #6c757d, #495057); }
            .badge { background: rgba(255,255,255,0.2); padding: 4px 10px; border-radius: 20px; font-size: 12px; margin-left: auto; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌿 Huerto Connect API</h1>
            <p class="sub">Microservicios FastAPI · MongoDB · PostgreSQL</p>
            <div class="links">
                <a href="/docs" class="btn swagger">
                    📖 Swagger UI — Documentación interactiva
                    <span class="badge">Probar API</span>
                </a>
                <a href="/redoc" class="btn redoc">
                    📄 ReDoc — Documentación de referencia
                    <span class="badge">Leer</span>
                </a>
                <a href="/api/health" class="btn health">
                    💚 Health Check — Estado de servicios
                    <span class="badge">JSON</span>
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# ===================== HEALTH CHECK =====================

@app.get("/api/health")
async def gateway_health():
    """Gateway health check — checks all services."""
    services_status = {}
    for name, svc in SERVICES.items():
        try:
            resp = await _http_client.get(f"{svc['url']}/api/health", timeout=5.0)
            services_status[name] = "ok" if resp.status_code == 200 else "error"
        except Exception:
            services_status[name] = "unreachable"

    all_ok = all(s == "ok" for s in services_status.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "gateway",
        "services": services_status,
    }


# ===================== REVERSE PROXY =====================

@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proxy(request: Request, path: str):
    """Reverse proxy — forward requests to the appropriate microservice."""
    full_path = f"/api/{path}"
    service_url = _find_service_url(full_path)

    if not service_url:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No service found for path: {full_path}"},
        )

    # Build target URL
    target_url = f"{service_url}{full_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Forward headers (including Authorization)
    headers = dict(request.headers)
    headers.pop("host", None)

    # Forward body
    body = await request.body()

    try:
        response = await _http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )

        # Strip hop-by-hop headers
        excluded_headers = {"transfer-encoding", "connection", "keep-alive"}
        response_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in excluded_headers
        }

        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
        )

    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Service unavailable. Please try again later."},
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"detail": "Service timeout. Please try again later."},
        )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"detail": f"Gateway error: {str(e)}"},
        )
