import io
import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
from threading import Lock
import httpx
import jwt
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from PIL import Image
from conftest import load_service
from shared.config import settings
from shared.auth.security import hash_token


async def identity(db):
    uid = ObjectId()
    await db.usuarios.insert_one({"_id": uid, "email": f"{uid}@example.com", "estado": "Activo", "role": "usuario"})
    token = jwt.encode({"sub": str(uid), "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, settings.JWT_SECRET, algorithm="HS256")
    await db.sesiones.insert_one({"token_hash": hash_token(token), "user_id": str(uid), "activa": True, "expires_at": datetime.now(timezone.utc)+timedelta(hours=1)})
    return {"id": str(uid), "rol": "Usuario"}, {"Authorization": f"Bearer {token}"}


def client(app, headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers)


def picture():
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(stream, format="PNG")
    return ("plant.png", stream.getvalue(), "image/png")


class FakeClassifier:
    names = {0: "pulgones", 1: "trips", 2: "arana_roja"}
    def __init__(self, values=(.9, .08, .02)):
        self.values = values
    def predict(self, *args, **kwargs):
        return [SimpleNamespace(probs=SimpleNamespace(data=SimpleNamespace(cpu=lambda: SimpleNamespace(tolist=lambda: self.values))))]


async def test_owner_inference_history_chat_report_flow():
    db = AsyncMongoMockClient(tz_aware=True).test
    owner, headers = await identity(db)
    other, other_headers = await identity(db)
    huertos = load_service("huertos-service")
    huertos.app.state.mongodb = db
    async with client(huertos.app, headers) as http:
        response = await http.post("/api/huertos", json={"nombre": "Prueba Veracruz", "municipio": "Xalapa"})
        assert response.status_code == 201, response.text
        hid = response.json()["id"]
        assert (await http.get(f"/api/huertos/{hid}")).status_code == 200
        assert (await http.get("/api/huertos/no-id")).status_code == 422
    async with client(huertos.app, other_headers) as http:
        assert (await http.get(f"/api/huertos/{hid}")).status_code == 404
        assert (await http.put(f"/api/huertos/{hid}", json={"nombre": "robado"})).status_code == 404
        assert (await http.delete(f"/api/huertos/{hid}")).status_code == 404
        assert (await http.get("/api/huertos")).json() == []

    ai = load_service("plagas-service")
    manager_module = importlib.import_module("app.ai.model_manager")
    manager = manager_module.ModelManager()
    manager.models = {"plaga": FakeClassifier(), "enfermedad": FakeClassifier()}
    ai.app.state.mongodb = db
    ai.app.state.models = manager
    async with client(ai.app, headers) as http:
        response = await http.post("/ai/plagas/predict", files={"imagen": picture()}, data={"huerto_id": hid})
        assert response.status_code == 200, response.text
        assert response.json()["clase"] == "pulgones"
        assert len(response.json()["top"]) == 3
        assert response.json()["diagnostico_id"]
        assert len((await http.get(f"/ai/diagnosticos/{hid}")).json()) == 1
        assert (await http.post("/ai/enfermedades/predict", files={"imagen": picture()})).status_code == 200
        manager.models["plaga"] = FakeClassifier((.5, .4, .1))
        assert not (await http.post("/ai/plagas/predict", files={"imagen": picture()})).json()["detectado"]
        manager.models.pop("plaga")
        assert (await http.post("/ai/plagas/predict", files={"imagen": picture()})).status_code == 503
        assert (await http.post("/ai/plagas/predict", files={"imagen": ("bad.png", b"not an image", "image/png")})).status_code == 422
        assert (await http.post("/ai/plagas/predict", files={"imagen": ("bad.txt", b"bad", "text/plain")})).status_code == 415
    async with client(ai.app, other_headers) as http:
        assert (await http.get(f"/ai/diagnosticos/{hid}")).status_code == 404
        assert (await http.post("/ai/plagas/predict", files={"imagen": picture()}, data={"huerto_id": hid})).status_code == 404

    chat = load_service("chat-service")
    chat.app.state.mongodb = db
    chat.app.state.agent_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"answer": "Revisa el envés de las hojas.", "status": "answered"})), base_url="http://agent")
    async with client(chat.app, headers) as http:
        response = await http.post("/api/agent/v1/chat", json={"message": "¿Cómo cuidar mis plantas?"})
        assert response.status_code == 200, response.text
        cid = response.json()["conversation_id"]
        assert len((await http.get(f"/api/chatbot/conversaciones/{cid}/mensajes")).json()) == 2
    async with client(chat.app, other_headers) as http:
        assert (await http.get(f"/api/chatbot/conversaciones/{cid}/mensajes")).status_code == 404
        assert (await http.post(f"/api/chatbot/conversaciones/{cid}/mensajes", json={"contenido": "intruso"})).status_code == 404
        assert (await http.post("/api/agent/v1/chat", json={"message": "hola", "conversation_id": cid})).status_code == 404
    await chat.app.state.agent_client.aclose()

    reports = load_service("reportes-service")
    reports.app.state.mongodb = db
    async with client(reports.app, headers) as http:
        response = await http.get(f"/api/reportes/huertos/{hid}/csv")
        assert response.status_code == 200 and "pulgones" in response.text
        pdf = await http.get(f"/api/reportes/huertos/{hid}/pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    async with client(reports.app, other_headers) as http:
        assert (await http.get(f"/api/reportes/huertos/{hid}/pdf")).status_code == 404
    async with client(reports.app) as http:
        assert (await http.get(f"/api/reportes/huertos/{hid}/csv")).status_code == 401


@pytest.mark.parametrize("error,status", [(httpx.ConnectError, 503), (httpx.ReadTimeout, 504)])
async def test_gateway_failures(error, status):
    gateway = load_service("gateway")
    def fail(request):
        raise error("private address must not leak")
    gateway._http_client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    async with client(gateway.app) as http:
        response = await http.get("/ai/health")
        assert response.status_code == status
        assert "private" not in response.text
    await gateway._http_client.aclose()


async def test_gateway_success_and_schemas():
    gateway = load_service("gateway")
    def success(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"paths": {"/example": {"get": {"responses": {"200": {"$ref": "#/components/schemas/Result"}}}}}, "components": {"schemas": {"Result": {"type": "object"}}}})
        return httpx.Response(422, json={"detail": "validation error"})
    gateway._http_client = httpx.AsyncClient(transport=httpx.MockTransport(success))
    async with client(gateway.app) as http:
        assert (await http.get("/ai/health")).status_code == 422
        spec = (await http.get("/openapi.json")).json()
        ref = spec["paths"]["/example"]["get"]["responses"]["200"]["$ref"].split("/")[-1]
        assert ref in spec["components"]["schemas"]
    await gateway._http_client.aclose()
