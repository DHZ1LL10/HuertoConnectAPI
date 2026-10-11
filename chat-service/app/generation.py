"""Chat owns history; Agent only generates responses."""
from datetime import datetime, timezone, timedelta
import uuid
import httpx
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from shared.auth.dependencies import get_current_user
from shared.config import settings
from shared.ownership import require_conversation_access

router = APIRouter(prefix="/api/agent/v1", tags=["Agent — historial en Chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


@router.post("/chat")
async def generate(body: ChatRequest, request: Request, user=Depends(get_current_user)):
    db = request.app.state.mongodb
    conv_id = body.conversation_id
    if conv_id:
        conv = await require_conversation_access(db, conv_id, user)
        if conv.get("estado") == "Cerrada":
            raise HTTPException(409, "Conversación cerrada")
    else:
        saved = await db.chat_conversaciones.insert_one({"usuario_id": user["id"], "tema": body.message[:100], "estado": "Activa", "fecha": datetime.now(timezone.utc)})
        conv_id = str(saved.inserted_id)
    now = datetime.now(timezone.utc)
    lease = await db.chat_conversaciones.update_one({"_id": ObjectId(conv_id), "$or": [{"busy_until": {"$exists": False}}, {"busy_until": {"$lt": now}}]}, {"$set": {"busy_until": now + timedelta(seconds=settings.AGENT_TIMEOUT_SECONDS + 30)}})
    if not lease.modified_count:
        raise HTTPException(409, "Ya hay una respuesta en curso")
    try:
        docs = await db.chat_mensajes.find({"conversacion_id": conv_id}).sort("fecha", -1).to_list(12)
        history = [{"role": m["rol"], "content": m["contenido"]} for m in reversed(docs)]
        response = await request.app.state.agent_client.post("/v1/generate", json={"message": body.message, "history": history}, headers={"X-API-Key": settings.AGENT_API_KEY, "X-User-ID": user["id"]})
        if response.status_code == 429:
            raise HTTPException(429, "El agente está ocupado. Intenta de nuevo.", headers={"Retry-After": "2"})
        if response.status_code != 200:
            raise HTTPException(504 if response.status_code == 504 else 503, "Agente no disponible")
        result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("answer"), str) or not result["answer"].strip() or result.get("status") not in {"answered", "blocked", "redirected"}:
            raise HTTPException(503, "El agente devolvió una respuesta inválida")
        answer = result["answer"]
        stamp = datetime.now(timezone.utc)
        await db.chat_mensajes.insert_many([
            {"conversacion_id": conv_id, "rol": "user", "contenido": body.message, "fecha": stamp},
            {"conversacion_id": conv_id, "rol": "assistant", "contenido": answer, "fecha": stamp + timedelta(milliseconds=1)},
        ])
        await db.chat_conversaciones.update_one({"_id": ObjectId(conv_id)}, {"$set": {"ultimo_mensaje": answer, "updated_at": stamp}})
        return {"answer": answer, "status": result["status"], "safety_reason": result.get("safety_reason"), "model": result.get("model"), "conversation_id": conv_id, "request_id": result.get("request_id") or str(uuid.uuid4())}
    except httpx.TimeoutException:
        raise HTTPException(504, "El agente excedió el tiempo de respuesta")
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503, "Agente no disponible")
    finally:
        await db.chat_conversaciones.update_one({"_id": ObjectId(conv_id)}, {"$unset": {"busy_until": ""}})


@router.get("/conversations/{conversation_id}/messages")
async def messages(conversation_id: str, request: Request, user=Depends(get_current_user)):
    await require_conversation_access(request.app.state.mongodb, conversation_id, user)
    docs = await request.app.state.mongodb.chat_mensajes.find({"conversacion_id": conversation_id}).sort("fecha", 1).to_list(200)
    return {"conversation_id": conversation_id, "messages": [{"role": m["rol"], "content": m["contenido"], "created_at": m["fecha"]} for m in docs]}


@router.delete("/conversations/{conversation_id}")
async def close(conversation_id: str, request: Request, user=Depends(get_current_user)):
    await require_conversation_access(request.app.state.mongodb, conversation_id, user)
    await request.app.state.mongodb.chat_conversaciones.update_one({"_id": ObjectId(conversation_id)}, {"$set": {"estado": "Cerrada"}})
    return {"conversation_id": conversation_id, "deleted": False, "estado": "Cerrada"}
