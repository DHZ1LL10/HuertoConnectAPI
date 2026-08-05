"""
API Gateway — Reverse proxy to all Huerto Connect microservices.
Single entry point for the frontend.
Unified Swagger UI at /docs with all services' endpoints.

Authentication for /api/agent/* routes:
  - Validates Bearer JWT (same token used for all other services)
  - Extracts user_id from the token 'sub' claim
  - Automatically injects X-User-ID + X-API-Key before forwarding to agent-service
  - Users never need to know about the internal X-API-Key
"""

from contextlib import asynccontextmanager

import httpx
import jwt as pyjwt
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
    "/api/agent": settings.AGENT_SERVICE_URL,
}

# Services for documentation aggregation and health checks
SERVICES = {
    "auth": {
        "url": settings.AUTH_SERVICE_URL,
        "label": "Auth Service",
        "health_path": "/api/health",
    },
    "huertos": {
        "url": settings.HUERTOS_SERVICE_URL,
        "label": "Huertos Service",
        "health_path": "/api/health",
    },
    "plagas": {
        "url": settings.PLAGAS_SERVICE_URL,
        "label": "Plagas/IA Service",
        "health_path": "/api/health",
    },
    "chat": {
        "url": settings.CHAT_SERVICE_URL,
        "label": "Chat Service",
        "health_path": "/api/health",
    },
    "reportes": {
        "url": settings.REPORTES_SERVICE_URL,
        "label": "Reportes Service",
        "health_path": "/api/health",
    },
    "agent": {
        "url": settings.AGENT_SERVICE_URL,
        "label": "Agent IA Service",
        "health_path": "/health/live",
    },
}

# Prefixes to strip before forwarding to the target service.
# Example: gateway receives /api/agent/v1/chat -> forwards /v1/chat to agent-service
STRIP_PREFIX_MAP: dict[str, str] = {
    "/api/agent": "/api/agent",
}

# Path prefix to ADD when merging a service's OpenAPI paths into the unified spec.
# This ensures that Swagger UI "Try it out" sends requests to the correct gateway URL.
# Only needed for services whose internal routes don't start with /api/<service>.
PATH_PREFIX_IN_DOCS: dict[str, str] = {
    "agent": "/api/agent",
}

# Routes that require JWT validation at the gateway level before forwarding.
# The gateway will extract user_id from the JWT and inject X-User-ID automatically.
AGENT_ROUTE_PREFIX = "/api/agent"

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
    # Default timeout 30s for all services; agent gets a per-request override
    # because Ollama inference on CPU can take several minutes.
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10.0,    # tiempo para establecer conexión
            read=310.0,      # tiempo de lectura — cubre gemma3:4b en CPU (OLLAMA_TIMEOUT_SECONDS=300 + margen)
            write=10.0,      # tiempo para enviar la petición
            pool=5.0,        # tiempo para obtener conexión del pool
        )
    )
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


# ===================== JWT HELPERS (Gateway-level) =====================

def _decode_jwt_payload(token: str) -> dict | None:
    """
    Decode a JWT token and return its payload without full session validation.
    The gateway only needs the 'sub' (user_id) to forward to the agent-service.
    Full session validation is done by each individual service.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def _extract_bearer_token(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def _get_user_id_from_request(request: Request) -> str | None:
    """
    Extract and validate the JWT from the request, returning the user_id (sub).
    Returns None if token is missing or invalid.
    """
    token = _extract_bearer_token(request)
    if not token:
        return None
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    return str(user_id).strip() if user_id else None


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
                "- Reportes (reportes, auditoría)\n"
                "- Agent IA (chat con Brot, historial de conversaciones, Ollama local)\n\n"
                "**Autenticación:** Usa `Bearer <JWT_TOKEN>` en el header Authorization.\n\n"
                "El gateway extrae automáticamente tu identidad del token para el Agent IA.\n\n"
                "**Roles:** `Admin`, `Usuario`, `Tecnico`"
            ),
            "version": "1.0.0",
        },
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "HTTPBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        "Token JWT obtenido al hacer login. "
                        "Se usa para autenticar todos los servicios de la API."
                    ),
                }
            },
        },
    }

    for name, svc in SERVICES.items():
        try:
            resp = await _http_client.get(f"{svc['url']}/openapi.json", timeout=5.0)
            if resp.status_code == 200:
                spec = resp.json()

                # Path prefix to add in the unified docs (e.g. /api/agent for agent-service)
                path_prefix = PATH_PREFIX_IN_DOCS.get(name, "")

                # Merge paths
                for path, methods in spec.get("paths", {}).items():
                    # Skip internal health paths for services that get a prefix,
                    # to avoid confusing duplicates like /api/agent/api/health
                    if path_prefix and path in {"/api/health", "/health/live", "/health/ready"}:
                        continue
                    # Tag all operations with service name
                    for method, operation in methods.items():
                        if isinstance(operation, dict):
                            tags = operation.get("tags", [])
                            # Prefix tags with service label for grouping
                            operation["tags"] = [f"{svc['label']} — {t}" for t in tags] if tags else [svc["label"]]
                            # Normalize all security requirements to HTTPBearer so single Authorize button works
                            if operation.get("security"):
                                operation["security"] = [{"HTTPBearer": []}]
                            elif name == "agent" and not path.startswith("/health"):
                                operation["security"] = [{"HTTPBearer": []}]

                    # Rewrite path so Swagger UI "Try it out" hits the correct gateway route
                    merged_path = f"{path_prefix}{path}" if path_prefix else path
                    merged["paths"][merged_path] = methods

                # Merge schemas (prefix to avoid collisions)
                for schema_name, schema_def in spec.get("components", {}).get("schemas", {}).items():
                    key = schema_name
                    if key in merged["components"]["schemas"]:
                        key = f"{name}_{schema_name}"
                    merged["components"]["schemas"][key] = schema_def

                # Merge additional security schemes if any (skip agent-specific X-API-Key)
                if name != "agent":
                    for scheme_name, scheme_def in spec.get("components", {}).get("securitySchemes", {}).items():
                        if scheme_name not in ("HTTPBearer", "BearerAuth"):
                            merged["components"]["securitySchemes"][scheme_name] = scheme_def

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
    """Comprueba el estado de todos los microservicios."""

    services_status = {}

    for name, svc in SERVICES.items():
        health_path = svc.get("health_path", "/api/health")
        health_url = f"{svc['url']}{health_path}"

        try:
            response = await _http_client.get(
                health_url,
                timeout=5.0,
            )

            services_status[name] = (
                "ok" if response.status_code == 200 else "error"
            )

        except httpx.ConnectError:
            services_status[name] = "unreachable"

        except httpx.TimeoutException:
            services_status[name] = "timeout"

        except Exception as exc:
            print(f"[HEALTH] Error comprobando {name}: {exc}")
            services_status[name] = "error"

    all_ok = all(
        status == "ok"
        for status in services_status.values()
    )

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

    # ── Agent-service JWT authentication ─────────────────────────────────────
    # For /api/agent/* routes we validate the JWT at the gateway level and
    # inject X-User-ID (from the token 'sub') + X-API-Key so the agent-service
    # can identify the user without the frontend ever needing to know the
    # internal API key. This keeps each user's conversations fully isolated.
    agent_injected_headers: dict[str, str] = {}
    if full_path.startswith(AGENT_ROUTE_PREFIX):
        # OPTIONS (CORS preflight) passes through without auth
        if request.method != "OPTIONS":
            user_id = _get_user_id_from_request(request)
            if user_id is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": (
                            "Token de autenticación requerido para el Agent IA. "
                            "Incluye el header: Authorization: Bearer <tu_jwt_token>"
                        )
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Inject the internal headers — never exposed to the end user
            agent_injected_headers["X-User-ID"] = user_id
            agent_injected_headers["X-API-Key"] = settings.AGENT_API_KEY

    # Build target URL — strip gateway prefix for services that manage their own routing
    matched_prefix = next(
        (prefix for prefix in sorted(SERVICE_MAP.keys(), key=len, reverse=True)
         if full_path.startswith(prefix)),
        None,
    )
    strip = STRIP_PREFIX_MAP.get(matched_prefix, "") if matched_prefix else ""
    forwarded_path = full_path[len(strip):] if strip and full_path.startswith(strip) else full_path
    if not forwarded_path:
        forwarded_path = "/"

    target_url = f"{service_url}{forwarded_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Forward headers (including Authorization)
    headers = dict(request.headers)
    headers.pop("host", None)
    # Apply agent-specific injected headers (overrides anything the client sent)
    headers.update(agent_injected_headers)

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
