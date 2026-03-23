"""
Chat Service — FastAPI Application
Microservice for chatbot conversations, messages, and metrics.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.auth.dependencies import get_current_user, require_roles
from shared.config import settings
from shared.database import close_mongodb, connect_mongodb


# ===================== SCHEMAS =====================

class ConversacionCreate(BaseModel):
    tema: str = Field(..., min_length=1)

    model_config = {
        "json_schema_extra": {
            "example": {
                "tema": "Control biológico para trips en jitomate",
            }
        }
    }


class ConversacionResponse(BaseModel):
    id: str
    usuario_id: str
    tema: str
    ultimo_mensaje: Optional[str] = None
    estado: str
    fecha: Optional[str] = None


class MensajeCreate(BaseModel):
    contenido: str = Field(..., min_length=1)
    rol: str = Field(default="user", pattern=r"^(user|assistant|system)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "contenido": "Tengo hojas plateadas y puntos negros en el envés, ¿qué podría ser?",
                "rol": "user",
            }
        }
    }


class MensajeResponse(BaseModel):
    id: str
    conversacion_id: str
    rol: str
    contenido: str
    fecha: Optional[str] = None


class MetricaResponse(BaseModel):
    id: str
    tema: str
    total: int
    porcentaje: float
    updated_at: Optional[str] = None


class MessageResponse(BaseModel):
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "Conversación cerrada",
            }
        }
    }


# ===================== ROUTES =====================

conversaciones_router = APIRouter(prefix="/api/chatbot", tags=["Chatbot"])


@conversaciones_router.get("/conversaciones", response_model=list[ConversacionResponse])
async def list_conversaciones(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """List conversations. Users see only their own."""
    db = request.app.state.mongodb
    query = {"usuario_id": current_user["id"]}
    if current_user["rol"] in ["Admin", "Tecnico"]:
        query = {}  # Admin/Tecnico see all

    cursor = db.chat_conversaciones.find(query).sort("fecha", -1).skip(skip).limit(limit)
    items = await cursor.to_list(limit)
    return [
        ConversacionResponse(
            id=str(c["_id"]),
            usuario_id=str(c["usuario_id"]),
            tema=c["tema"],
            ultimo_mensaje=c.get("ultimo_mensaje"),
            estado=c.get("estado", "Activa"),
            fecha=c.get("fecha", "").isoformat() if c.get("fecha") else None,
        )
        for c in items
    ]


@conversaciones_router.post("/conversaciones", response_model=ConversacionResponse, status_code=201)
async def create_conversacion(
    body: ConversacionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Start a new chatbot conversation."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)
    doc = {
        "usuario_id": current_user["id"],
        "tema": body.tema,
        "ultimo_mensaje": None,
        "estado": "Activa",
        "fecha": now,
        "updated_at": now,
    }
    result = await db.chat_conversaciones.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ConversacionResponse(
        id=str(doc["_id"]),
        usuario_id=current_user["id"],
        tema=doc["tema"],
        ultimo_mensaje=None,
        estado="Activa",
        fecha=now.isoformat(),
    )


@conversaciones_router.get("/conversaciones/{conv_id}/mensajes", response_model=list[MensajeResponse])
async def list_mensajes(
    conv_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List messages in a conversation."""
    db = request.app.state.mongodb
    items = await db.chat_mensajes.find(
        {"conversacion_id": conv_id}
    ).sort("fecha", 1).to_list(200)
    return [
        MensajeResponse(
            id=str(m["_id"]),
            conversacion_id=m["conversacion_id"],
            rol=m["rol"],
            contenido=m["contenido"],
            fecha=m.get("fecha", "").isoformat() if m.get("fecha") else None,
        )
        for m in items
    ]


@conversaciones_router.post("/conversaciones/{conv_id}/mensajes", response_model=MensajeResponse, status_code=201)
async def create_mensaje(
    conv_id: str,
    body: MensajeCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Add a message to a conversation."""
    db = request.app.state.mongodb
    now = datetime.now(timezone.utc)

    msg_doc = {
        "conversacion_id": conv_id,
        "rol": body.rol,
        "contenido": body.contenido,
        "fecha": now,
    }
    result = await db.chat_mensajes.insert_one(msg_doc)

    # Update conversation's last message
    await db.chat_conversaciones.update_one(
        {"_id": ObjectId(conv_id)},
        {"$set": {"ultimo_mensaje": body.contenido, "updated_at": now}},
    )

    return MensajeResponse(
        id=str(result.inserted_id),
        conversacion_id=conv_id,
        rol=body.rol,
        contenido=body.contenido,
        fecha=now.isoformat(),
    )


@conversaciones_router.patch("/conversaciones/{conv_id}/cerrar", response_model=MessageResponse)
async def close_conversacion(
    conv_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Close a conversation."""
    db = request.app.state.mongodb
    result = await db.chat_conversaciones.update_one(
        {"_id": ObjectId(conv_id)},
        {"$set": {"estado": "Cerrada", "updated_at": datetime.now(timezone.utc)}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return MessageResponse(message="Conversación cerrada")


@conversaciones_router.get("/metricas", response_model=list[MetricaResponse])
async def list_metricas(
    request: Request,
    current_user: dict = Depends(require_roles(["Admin", "Tecnico"])),
):
    """Get chatbot usage metrics."""
    db = request.app.state.mongodb
    items = await db.chat_metricas.find().to_list(50)
    return [
        MetricaResponse(
            id=str(m["_id"]),
            tema=m["tema"],
            total=m.get("total", 0),
            porcentaje=m.get("porcentaje", 0),
            updated_at=m.get("updated_at", "").isoformat() if m.get("updated_at") else None,
        )
        for m in items
    ]


# ===================== APP =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("💬 Chat Service starting...")
    db = await connect_mongodb()
    app.state.mongodb = db
    print(f"  ✅ Connected to MongoDB: {settings.MONGO_DB}")
    print("  📖 Swagger UI: http://localhost:8004/docs")
    print("💬 Chat Service ready on port 8004")
    yield
    await close_mongodb()
    print("💬 Chat Service stopped.")


app = FastAPI(
    title="Huerto Connect — Chat Service",
    description="Microservicio de chatbot: conversaciones, mensajes, métricas",
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

app.include_router(conversaciones_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "chat-service"}
