"""Real HTTP/DB smoke against reportes-service/compose.test.yml only."""
import asyncio
from datetime import datetime, timedelta, timezone
import uuid
from pathlib import Path
import httpx
import jwt
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

KEY = "reportes-test-only-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


async def main():
    mongo = AsyncIOMotorClient("mongodb://127.0.0.1:27030", serverSelectionTimeoutMS=5000)
    db = mongo.reportes_smoke
    uid, other, hid = ObjectId(), ObjectId(), ObjectId()
    headers = []
    try:
        for user_id in (uid, other):
            jti = str(uuid.uuid4())
            token = jwt.encode({"sub": str(user_id), "jti": jti, "exp": datetime.now(timezone.utc)+timedelta(minutes=10)}, KEY, algorithm="HS256")
            await db.usuarios.insert_one({"_id": user_id, "email": f"{user_id}@example.invalid", "nombre": "Smoke", "estado": "Activo", "rol": "Admin"})
            await db.sesiones.insert_one({"jti": jti, "user_id": str(user_id), "activa": True, "expires_at": datetime.now(timezone.utc)+timedelta(minutes=10)})
            headers.append({"Authorization": f"Bearer {token}"})
        await db.huertos.insert_one({"_id": hid, "usuario_id": str(uid), "nombre": "Huerto de prueba - Café y cítricos", "municipio": "Xalapa"})
        await db.diagnosticos.insert_many([{"huerto_id": str(hid), "usuario_id": str(uid), "fecha": datetime(2026, 9, 13, tzinfo=timezone.utc), "tipo": "plaga", "clase": "pulgones", "confianza": .91, "detectado": True, "modelo": "yolo_plagas_veracruz_v6", "version": "v6", "nota": "La clasificación no sustituye un diagnóstico agronómico."} for _ in range(40)])
        async with httpx.AsyncClient(base_url="http://127.0.0.1:18005", headers=headers[0], timeout=20, trust_env=False) as client:
            for path in ("/health/ready", "/docs"):
                response = await client.get(path)
                assert response.status_code == 200, (path, response.text)
            prefix = f"/api/reportes/huertos/{hid}"
            assert (await client.get(prefix + "/pdf", headers=headers[1])).status_code == 404
            assert (await client.get(prefix + "/estadisticas/resumen")).json()["total"] == 40
            response = await client.get(prefix + "/csv?limite=1")
            assert response.status_code == 200 and response.headers["x-report-truncated"] == "true"
            pdf = await client.get(prefix + "/pdf")
            assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
            preview = Path(__file__).resolve().parents[1] / "tmp/pdfs"
            preview.mkdir(parents=True, exist_ok=True)
            (preview / "reportes-qa.pdf").write_bytes(pdf.content)
            import fitz
            with fitz.open(stream=pdf.content, filetype="pdf") as document:
                for index, page in enumerate(document):
                    page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25)).save(str(preview / f"reportes-qa-{index+1}.png"))
                print("PDF QA pages:", len(document))
            result = await client.post("/api/reportes", json={"nombre": "smoke-report", "tipo": "csv", "archivo_url": "https://example.com/report.csv"})
            assert result.status_code == 201, result.text
            rid = result.json()["id"]
            try:
                assert result.json()["estado"] == "Listo"
                assert (await client.get("/api/reportes", headers=headers[1])).json() == []
                assert (await client.delete(f"/api/reportes/{rid}", headers=headers[1])).status_code == 404
                assert (await client.delete("/api/reportes/not-uuid")).status_code == 422
            finally:
                assert (await client.delete(f"/api/reportes/{rid}")).status_code == 200
            logs = (await client.get("/api/auditoria", params={"actor_id": str(uid)})).json()
            assert {log["accion"] for log in logs} == {"crear_reporte", "eliminar_reporte"}
            print("Reportes smoke OK: Docker, migrations, real Mongo/PostgreSQL, CSV/PDF, ownership and audit")
    finally:
        await db.diagnosticos.delete_many({"usuario_id": str(uid)})
        await db.reporte_exportaciones.delete_many({"usuario_id": str(uid)})
        await db.huertos.delete_one({"_id": hid})
        for user_id in (uid, other):
            await db.sesiones.delete_many({"user_id": str(user_id)})
            await db.usuarios.delete_one({"_id": user_id})
        mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
