"""Real local API smoke with disposable identities; no OTP emails or production history."""
import asyncio
import argparse
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bson import ObjectId
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from shared.config import settings
from shared.auth.security import create_jwt_token, hash_token


async def check(storage=False, chat=False):
    mongo = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo[settings.MONGO_DB]
    uid, hid = ObjectId(), ObjectId()
    email = str(uid) + "@example.invalid"
    token = create_jwt_token(str(uid), email, "Usuario")
    uploaded = []
    try:
        await db.usuarios.insert_one({"_id": uid, "email": email, "nombre": "Prueba IA", "role": "usuario", "estado": "Activo"})
        await db.sesiones.insert_one({"token_hash": hash_token(token), "usuario_id": str(uid), "activa": True,
                                      "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
        await db.huertos.insert_one({"_id": hid, "nombre": "Prueba IA", "usuario_id": str(uid), "municipio": "Xalapa"})
        async with httpx.AsyncClient(base_url="http://gateway:8000", timeout=120, trust_env=False,
                                     headers={"Authorization": "Bearer " + token}) as client:
            regions = await client.get("/api/regiones")
            regions.raise_for_status()
            assert len(regions.json()) == 10
            image = io.BytesIO()
            Image.new("RGB", (640, 640), "green").save(image, format="PNG")
            for kind in ("plagas", "enfermedades"):
                start = time.perf_counter()
                response = await client.post(f"/ai/{kind}/predict", data={"huerto_id": str(hid), "guardar_imagen": "true" if storage and kind == "enfermedades" else "false"},
                                              files={"imagen": ("prueba.png", image.getvalue(), "image/png")})
                assert response.status_code == 200, (kind, response.status_code, response.text[:200])
                result = response.json()
                if result.get("imagen_file_id"):
                    uploaded.append(result["imagen_file_id"])
                    # Never forward the API user's JWT to an external image host.
                    async with httpx.AsyncClient(timeout=30, trust_env=False) as delivery:
                        original = await delivery.get(result["imagen_url"])
                    original.raise_for_status()
                    assert original.content == image.getvalue(), "ImageKit debe preservar los bytes originales"
                assert result["top"] and result["diagnostico_id"] and result["recomendaciones"]
                print({"flujo": kind, "status": response.status_code, "seconds": round(time.perf_counter()-start, 3)})
            options = await client.get("/ai/rendimiento/opciones")
            options.raise_for_status()
            categories = options.json()["categorias"]
            features = {name: values[0] for name, values in categories.items()}
            features["Anio"] = 2026
            start = time.perf_counter()
            predicted = await client.post("/ai/rendimiento/predict", json=features)
            assert predicted.status_code == 200, predicted.text[:200]
            assert predicted.json()["rendimiento"] >= 0
            print({"flujo": "random_forest", "status": 200, "seconds": round(time.perf_counter()-start, 3)})
            spec = (await client.get("/openapi.json")).json()["paths"]
            assert "/ai/rendimiento/opciones" in spec and "/ai/rendimiento/predict" in spec
            for path in ("/api/modelos", "/api/plagas", "/api/predicciones", "/api/recomendaciones", "/api/huertos/recomendar"):
                assert path not in spec, path
            print({"swagger": "ok", "regiones": 10, "nota": "Prueba funcional con imagen sintética; no mide precisión agronómica"})
            if chat:
                start = time.perf_counter()
                response = await client.post("/api/agent/v1/chat", json={"message": "Como cultivo jitomate en maceta?"})
                assert response.status_code == 200, response.text[:200]
                result = response.json()
                assert result["answer"] and result["conversation_id"]
                print({"flujo": "chat_gateway", "status": 200, "modelo": result["model"],
                       "seconds": round(time.perf_counter()-start, 2)})
    finally:
        conversations = await db.chat_conversaciones.find({"usuario_id": str(uid)}).to_list(None)
        await db.chat_mensajes.delete_many({"conversacion_id": {"$in": [str(c["_id"]) for c in conversations]}})
        await db.chat_conversaciones.delete_many({"usuario_id": str(uid)})
        await db.diagnosticos.delete_many({"usuario_id": str(uid)})
        await db.sesiones.delete_many({"usuario_id": str(uid)})
        await db.huertos.delete_one({"_id": hid})
        await db.usuarios.delete_one({"_id": uid})
        mongo.close()
        if uploaded:
            async with httpx.AsyncClient(timeout=30, trust_env=False) as cleanup:
                for file_id in uploaded:
                    response = await cleanup.delete("https://api.imagekit.io/v1/files/" + file_id,
                                                    auth=httpx.BasicAuth(settings.IMAGEKIT_PRIVATE_KEY, ""))
                    response.raise_for_status()
                print({"imagekit": "original verificado; archivos temporales eliminados", "archivos": len(uploaded)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", action="store_true", help="Prueba también una subida real a ImageKit y elimina únicamente ese archivo temporal")
    parser.add_argument("--chat", action="store_true", help="Mide una consulta pública del chat; elimina solo su conversación temporal")
    args = parser.parse_args()
    asyncio.run(check(args.storage, args.chat))
