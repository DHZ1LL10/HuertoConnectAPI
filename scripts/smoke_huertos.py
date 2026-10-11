"""Smoke against the isolated huertos-service/compose.test.yml stack."""
import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import httpx
import jwt
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

KEY = "huertos-test-only-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


async def main():
    mongo = AsyncIOMotorClient("mongodb://127.0.0.1:27029", serverSelectionTimeoutMS=5000)
    db = mongo.huertos_smoke
    uid, other = ObjectId(), ObjectId()
    created = {}
    try:
        headers = []
        for user_id in (uid, other):
            jti = str(uuid.uuid4())
            token = jwt.encode({"sub": str(user_id), "jti": jti, "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, KEY, algorithm="HS256")
            await db.usuarios.insert_one({"_id": user_id, "email": f"{user_id}@example.invalid", "nombre": "Smoke", "estado": "Activo", "rol": "Admin"})
            await db.sesiones.insert_one({"jti": jti, "user_id": str(user_id), "activa": True, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
            headers.append({"Authorization": f"Bearer {token}"})
        async with httpx.AsyncClient(base_url="http://127.0.0.1:18002", headers=headers[0], timeout=10, trust_env=False) as client:
            for route in ("/health/ready", "/health", "/docs"):
                result = await client.get(route)
                assert result.status_code == 200, (route, result.text)
            for collection, route, body in [
                ("regiones", "/api/regiones", {"nombre": f"smoke-{uid}"}),
                ("cultivos", "/api/cultivos", {"nombre": f"smoke-{uid}"}),
            ]:
                result = await client.post(route, json=body)
                assert result.status_code == 201, result.text
                created[collection] = result.json()["id"]
            result = await client.post("/api/huertos", json={"nombre": "Smoke huerto", "region_id": created["regiones"], "municipio": "Xalapa"})
            assert result.status_code == 201, result.text
            hid = created["huertos"] = result.json()["id"]
            assert (await client.get(f"/api/huertos/{hid}", headers=headers[1])).status_code == 404
            assert (await client.put(f"/api/huertos/{hid}", json={"salud": 80})).status_code == 200
            result = await client.post("/api/cultivos/siembras", json={"huerto_id": hid, "cultivo_id": created["cultivos"], "fecha_siembra": "2026-09-13"})
            assert result.status_code == 201, result.text
            created["huerto_cultivos"] = result.json()["id"]
            assert len((await client.get(f"/api/cultivos/siembras/{hid}")).json()) == 1
            assert (await client.get(f"/api/cultivos/siembras/{hid}", headers=headers[1])).status_code == 404
            assert (await client.delete(f"/api/cultivos/{created['cultivos']}")).status_code == 409
            assert (await client.delete(f"/api/huertos/{hid}")).status_code == 200
            assert (await client.get(f"/api/huertos/{hid}")).status_code == 404
            assert await db.huertos.find_one({"_id": ObjectId(hid), "deleted_at": {"$ne": None}})
            print("Huertos smoke OK: Docker HTTP, MongoDB real, JWT, CRUD, siembras, ownership and soft delete")
    finally:
        for collection, identifier in created.items():
            await db[collection].delete_one({"_id": ObjectId(identifier)})
        for user_id in (uid, other):
            await db.sesiones.delete_many({"user_id": str(user_id)})
            await db.usuarios.delete_one({"_id": user_id})
        mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
