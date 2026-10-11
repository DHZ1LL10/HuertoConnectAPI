"""Verify Community through Gateway using disposable identities and exact cleanup."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

from shared.auth.security import create_jwt_token, hash_token
from shared.config import settings
from shared.services.image_storage import delete_image

BASE = "/api/comunidad"


async def check(gateway, storage=False):
    mongo = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000, tz_aware=True)
    db = mongo[settings.MONGO_DB]
    user_ids = [ObjectId(), ObjectId()]
    post_ids = []
    tokens = []
    uploaded = []
    cleanup_errors = []
    try:
        for uid, role in zip(user_ids, ["Usuario", "Admin"]):
            email = str(uid) + "@example.invalid"
            token = create_jwt_token(str(uid), email, role)
            tokens.append(token)
            await db.usuarios.insert_one({"_id": uid, "email": email, "nombre": "Prueba temporal Comunidad", "role": role, "estado": "Activo"})
            await db.sesiones.insert_one({"token_hash": hash_token(token), "user_id": str(uid), "activa": True,
                                          "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
        admin = {"Authorization": "Bearer " + tokens[1]}
        async with httpx.AsyncClient(base_url=gateway, timeout=60, trust_env=False, headers={"Authorization": "Bearer " + tokens[0]}) as client:
            options = await client.get(BASE + "/opciones")
            assert options.status_code == 200 and len(options.json()["regiones"]) == 10
            response = await client.post(BASE + "/publicaciones", json={"titulo": "Prueba temporal de comunidad",
                "contenido": "Verificación funcional; este registro se elimina al terminar.", "tipo": "Pregunta", "region": "Capital", "cultivo": "Jitomate"})
            response.raise_for_status()
            pid = response.json()["id"]
            post_ids.append(pid)
            response = await client.post(BASE + f"/publicaciones/{pid}/comentarios", json={"contenido": "Comentario temporal"})
            assert response.status_code == 201
            for _ in range(2):
                response = await client.put(BASE + f"/publicaciones/{pid}/me-gusta")
                assert response.status_code == 200 and response.json()["total_me_gusta"] == 1
            response = await client.get(BASE + "/publicaciones", params={"solo_mias": "true", "region": "Capital", "cultivo": "jitomate", "limit": 1})
            response.raise_for_status()
            assert response.json()["items"][0]["id"] == pid and "contenido" not in response.json()["items"][0]
            if storage:
                source = io.BytesIO()
                Image.new("RGB", (640, 640), "green").save(source, format="PNG")
                original = source.getvalue()
                response = await client.post(BASE + f"/publicaciones/{pid}/fotos", files={"foto": ("temporal.png", original, "image/png")})
                # Track server-created file IDs even if validation below fails.
                doc = await db.comunidad_publicaciones.find_one({"_id": ObjectId(pid)})
                uploaded.extend(f["file_id"] for f in doc.get("fotos", []))
                assert response.status_code == 201
                async with httpx.AsyncClient(timeout=30, trust_env=False) as delivery:
                    downloaded = await delivery.get(response.json()["url"], headers={"Accept-Encoding": "identity"})
                    downloaded.raise_for_status()
                assert downloaded.content == original, "Los bytes originales deben conservarse"
                print("ImageKit: foto original verificada byte a byte")
            moderation = BASE + f"/publicaciones/{pid}/moderacion"
            response = await client.patch(moderation, headers=admin, json={"estado": "Oculta", "motivo": "Prueba temporal de moderación"})
            assert response.status_code == 200
            feed = await client.get(BASE + "/publicaciones", headers=admin)
            feed.raise_for_status()
            assert all(item["id"] != pid for item in feed.json()["items"])
            assert (await client.get(BASE + f"/publicaciones/{pid}/comentarios", headers=admin)).status_code == 200
            response = await client.patch(moderation, headers=admin, json={"estado": "Publicada", "motivo": "Fin de prueba temporal"})
            assert response.status_code == 200
            response = await client.get(BASE + f"/moderacion/publicaciones/{pid}", headers=admin)
            assert response.status_code == 200 and len(response.json()["historial"]) == 2
            spec = (await client.get("/openapi.json")).json()
            assert BASE + "/publicaciones" in spec["paths"] and BASE + "/publicaciones/{publicacion_id}/fotos" in spec["paths"]
            assert (await client.delete(BASE + f"/publicaciones/{pid}")).status_code == 200
            assert (await client.get(BASE + f"/publicaciones/{pid}/comentarios")).status_code == 404
            print("Gateway/Swagger: publicaciones, filtros, comentarios, me gusta y moderación verificados")
    finally:
        # If POST succeeded but a later assertion/network read failed, include only
        # records authored by this invocation's newly allocated temporary identity.
        try:
            own_docs = await db.comunidad_publicaciones.find({"autor.id": str(user_ids[0])}).to_list(None)
            post_ids = list(set(post_ids + [str(doc["_id"]) for doc in own_docs]))
            uploaded = list(set(uploaded + [photo["file_id"] for doc in own_docs for photo in doc.get("fotos", [])]))
        except Exception:
            cleanup_errors.append("localizar publicaciones temporales")
        for file_id in uploaded:
            try:
                await delete_image(file_id)
            except RuntimeError:
                cleanup_errors.append("eliminar imagen temporal de ImageKit")
        try:
            await db.comunidad_comentarios.delete_many({"publicacion_id": {"$in": post_ids}})
            await db.comunidad_me_gusta.delete_many({"publicacion_id": {"$in": post_ids}})
            await db.comunidad_publicaciones.delete_many({"_id": {"$in": [ObjectId(pid) for pid in post_ids]}})
            await db.sesiones.delete_many({"user_id": {"$in": [str(uid) for uid in user_ids]}})
            await db.usuarios.delete_many({"_id": {"$in": user_ids}})
        except Exception:
            cleanup_errors.append("eliminar registros temporales de MongoDB")
        finally:
            mongo.close()
        if cleanup_errors:
            raise RuntimeError("Limpieza incompleta: " + "; ".join(cleanup_errors))
        print("Limpieza: únicamente identidades, contenido e imágenes temporales de esta ejecución eliminados")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://gateway:8000")
    parser.add_argument("--storage", action="store_true", help="Sube y elimina una foto sintética real en ImageKit")
    args = parser.parse_args()
    try:
        asyncio.run(check(args.gateway, args.storage))
    except Exception as exc:
        # Never print response bodies, JWTs, database URLs or provider secrets.
        print("Prueba fallida:", type(exc).__name__)
        sys.exit(1)
