"""Real models + isolated databases from plagas-service/compose.test.yml only."""
import asyncio
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "plagas-service"), str(ROOT)]
# Deliberately fixed local test targets. Never use the project's production DBs.
os.environ.update({
    "MONGO_URI": "mongodb://127.0.0.1:27028", "MONGO_DB": "plagas_smoke",
    "POSTGRES_URI": "postgresql://plagas_test:local-test-only@127.0.0.1:55433/plagas_test",
    "JWT_SECRET": "smoke-jwt-" + "x" * 64, "OTP_HASH_SECRET": "smoke-otp-" + "x" * 64,
    "AGENT_API_KEY": "smoke-agent-" + "x" * 64, "ENVIRONMENT": "testing",
    "PLAGUE_MODEL_PATH": str(ROOT / "plagas-service/app/models/ml/yolo_plagas_veracruz_v6.pt"),
    "DISEASE_MODEL_PATH": str(ROOT / "plagas-service/app/models/ml/yolo_enfermedades_veracruz_v6.pt"),
    "RF_MODEL_PATH": str(ROOT / "huertos-service/app/models/ml/random_forest_veracruz.joblib"),
    "AI_DEVICE": "cpu",
})
import httpx
import jwt
from bson import ObjectId
from PIL import Image
from app.main import app
from shared.config import settings
from shared.auth.security import hash_token


async def main():
    async with app.router.lifespan_context(app):
        db = app.state.mongodb
        uid, hid = ObjectId(), ObjectId()
        token = jwt.encode({"sub": str(uid), "jti": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, settings.JWT_SECRET, algorithm="HS256")
        await db.usuarios.insert_one({"_id": uid, "email": f"{uid}@example.invalid", "estado": "Activo", "role": "tecnico"})
        await db.sesiones.insert_one({"token_hash": hash_token(token), "user_id": str(uid), "activa": True, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
        await db.huertos.insert_one({"_id": hid, "usuario_id": str(uid)})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
                for path in ("/health/ready", "/health", "/ai/health", "/docs"):
                    response = await client.get(path)
                    assert response.status_code == 200, (path, response.text)
                stream = io.BytesIO()
                Image.new("RGB", (320, 320), "green").save(stream, format="PNG")
                for kind in ("plagas", "enfermedades"):
                    classes = (await client.get(f"/ai/{kind}/classes")).json()["clases"]
                    result = await client.post(f"/ai/{kind}/predict", files={"imagen": ("synthetic.png", stream.getvalue(), "image/png")}, data={"huerto_id": str(hid)})
                    assert result.status_code == 200, result.text
                    data = result.json()
                    assert len(data["top"]) == min(3, len(classes)) and data["diagnostico_id"]
                    print(kind, "classes=", len(classes), "inference=OK; synthetic input, not an accuracy test")
                assert len((await client.get(f"/ai/diagnosticos/{hid}")).json()) == 2
                result = await client.post("/api/plagas", json={"plaga": "smoke-only", "huerto_id": str(hid), "confianza": 90})
                assert result.status_code == 201, result.text
                det_id = result.json()["id"]
                try:
                    assert (await client.patch(f"/api/plagas/{det_id}", json={"estado": "Confirmada"})).status_code == 200
                    assert (await client.patch("/api/plagas/invalid", json={"estado": "Confirmada"})).status_code == 422
                    assert len((await client.get("/api/plagas")).json()) == 1
                finally:
                    assert (await client.delete(f"/api/plagas/{det_id}")).status_code == 200
                print("Plagas smoke OK: real models, Mongo history, PostgreSQL CRUD, migrations, JWT and readiness")
        finally:
            await db.diagnosticos.delete_many({"usuario_id": str(uid)})
            await db.huertos.delete_one({"_id": hid})
            await db.sesiones.delete_many({"user_id": str(uid)})
            await db.usuarios.delete_one({"_id": uid})


if __name__ == "__main__":
    asyncio.run(main())
