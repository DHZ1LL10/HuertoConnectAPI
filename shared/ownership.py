"""Ownership checks shared by every resource service."""
from bson import ObjectId
from fastapi import HTTPException


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(422, "Identificador inválido")
    return ObjectId(value)


async def require_huerto_access(db, huerto_id: str, user: dict) -> dict:
    huerto = await db.huertos.find_one({"_id": object_id(huerto_id), "deleted_at": None})
    if not huerto or str(huerto.get("usuario_id")) != user["id"]:
        raise HTTPException(404, "Huerto no encontrado")
    return huerto


async def require_conversation_access(db, conversation_id: str, user: dict) -> dict:
    conversation = await db.chat_conversaciones.find_one({
        "_id": object_id(conversation_id), "usuario_id": user["id"],
    })
    if not conversation:
        raise HTTPException(404, "Conversación no encontrada")
    return conversation


async def owned_huerto_ids(db, user: dict) -> list[str]:
    cursor = db.huertos.find({"usuario_id": {"$in": [user["id"], object_id(user["id"])]}, "deleted_at": None}, {"_id": 1})
    return [str(item["_id"]) async for item in cursor]
