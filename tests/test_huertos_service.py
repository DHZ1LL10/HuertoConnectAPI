import importlib
from datetime import datetime, timezone
import httpx
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from conftest import load_service
from test_integration import identity


@pytest.fixture(scope="module")
def module():
    return load_service("huertos-service")


@pytest.fixture
async def api(module):
    db = AsyncMongoMockClient(tz_aware=True).huertos
    owner, headers = await identity(db)
    other, other_headers = await identity(db)
    module.app.state.mongodb = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test", headers=headers) as client:
        yield client, db, owner, other, other_headers


@pytest.mark.parametrize("role", ["Usuario", "Tecnico", "Admin"])
async def test_huerto_ownership_and_soft_delete(api, role):
    client, db, owner, other, foreign = api
    await db.usuarios.update_one({"_id": ObjectId(other["id"])}, {"$set": {"rol": role}})
    response = await client.post("/api/huertos", json={"nombre": "Mi huerto", "municipio": "Xalapa"})
    assert response.status_code == 201, response.text
    hid = response.json()["id"]
    assert response.json()["usuario_id"] == owner["id"]
    for method, body in [("GET", None), ("PUT", {"nombre": "intruso"}), ("DELETE", None)]:
        assert (await client.request(method, f"/api/huertos/{hid}", headers=foreign, json=body)).status_code == 404
    assert (await client.get("/api/huertos", headers=foreign)).json() == []
    assert (await client.put(f"/api/huertos/{hid}", json={"salud": 50})).status_code == 200
    assert (await client.delete(f"/api/huertos/{hid}")).status_code == 200
    assert (await client.get(f"/api/huertos/{hid}")).status_code == 404
    assert (await client.get("/api/huertos")).json() == []
    assert (await db.huertos.find_one({"_id": ObjectId(hid)}))["deleted_at"]


@pytest.mark.parametrize("body", [{"nombre": " "}, {"nombre": "x", "salud": -1}, {"nombre": "x", "estado": "invalid"}, {"nombre": "x", "usuario_id": "attacker"}])
async def test_invalid_create(api, body):
    assert (await api[0].post("/api/huertos", json=body)).status_code == 422


async def test_siembras_and_references(api):
    client, db, owner, other, foreign = api
    assert (await client.post("/api/huertos", json={"nombre": "x", "region_id": str(ObjectId())})).status_code == 404
    hid = (await client.post("/api/huertos", json={"nombre": "x"})).json()["id"]
    cid = (await client.post("/api/cultivos", json={"nombre": "Jitomate"})).json()["id"]
    body = {"huerto_id": hid, "cultivo_id": cid, "fecha_siembra": "2026-09-13"}
    assert (await client.post("/api/cultivos/siembras", json={**body, "cultivo_id": str(ObjectId())})).status_code == 404
    assert (await client.post("/api/cultivos/siembras", json={**body, "fecha_siembra": "invalid"})).status_code == 422
    assert (await client.post("/api/cultivos/siembras", json=body, headers=foreign)).status_code == 404
    assert (await client.post("/api/cultivos/siembras", json=body)).status_code == 201
    assert len((await client.get(f"/api/cultivos/siembras/{hid}")).json()) == 1
    assert (await client.get(f"/api/cultivos/siembras/{hid}", headers=foreign)).status_code == 404
    await db.usuarios.update_one({"_id": ObjectId(owner["id"])}, {"$set": {"rol": "Admin"}})
    assert (await client.delete(f"/api/cultivos/{cid}")).status_code == 409
    assert (await client.put(f"/api/cultivos/{cid}", json={"activo": False})).status_code == 200
    assert (await client.post("/api/cultivos/siembras", json=body)).status_code == 404


async def test_region_plantios_do_not_leak(api):
    client, db, owner, other, foreign = api
    rid = (await client.post("/api/regiones", json={"nombre": "Las Montañas"})).json()["id"]
    for user in (owner, other):
        hid = str((await db.huertos.insert_one({"nombre": "huerto", "region_id": rid, "usuario_id": user["id"]})).inserted_id)
        sid = str((await db.huerto_cultivos.insert_one({"huerto_id": hid})).inserted_id)
        await db.plantios.insert_one({"nombre": user["id"], "huerto_cultivo_id": sid})
    response = await client.get(f"/api/regiones/{rid}/plantios")
    assert response.status_code == 200, response.text
    assert [p["nombre"] for p in response.json()] == [owner["id"]]
    await db.usuarios.update_one({"_id": ObjectId(owner["id"])}, {"$set": {"rol": "Admin"}})
    assert (await client.delete(f"/api/regiones/{rid}")).status_code == 409


async def test_dataset_ownership(api):
    client, db, owner, other, foreign = api
    for user in (owner, other):
        await db.usuarios.update_one({"_id": ObjectId(user["id"])}, {"$set": {"rol": "Tecnico"}})
    hid = (await client.post("/api/huertos", json={"nombre": "x"})).json()["id"]
    body = {"imagen_url": "https://example.com/plant.png", "huerto_id": hid}
    assert (await client.post("/api/datasets/imagenes", json=body, headers=foreign)).status_code == 404
    assert (await client.post("/api/datasets/imagenes", json=body)).status_code == 201
    assert (await client.get("/api/datasets/imagenes", headers=foreign)).json() == []
    assert len((await client.get("/api/datasets/imagenes")).json()) == 1


async def test_notification_isolation(api):
    client, db, owner, other, foreign = api
    nid = str((await db.notificaciones_usuario.insert_one({"usuario_id": owner["id"], "titulo": "x", "mensaje": "x", "leida": False})).inserted_id)
    assert (await client.get("/api/notificaciones", headers=foreign)).json() == []
    assert (await client.patch(f"/api/notificaciones/{nid}/leer", headers=foreign)).status_code == 404
    assert (await client.patch(f"/api/notificaciones/{nid}/leer")).status_code == 200


async def test_validation_auth_and_profile(api, module):
    client, db, owner, other, foreign = api
    assert (await client.get("/api/huertos", headers={"Authorization": ""})).status_code == 401
    assert (await client.get("/api/huertos/invalid")).status_code == 422
    hid = (await client.post("/api/huertos", json={"nombre": "x"})).json()["id"]
    assert (await client.put(f"/api/huertos/{hid}", json={"salud": 101})).status_code == 422
    assert (await client.put(f"/api/huertos/{hid}", json={})).status_code == 400
    assert (await client.patch(f"/api/usuarios/{owner['id']}", json={"email": "new@example.com"})).status_code == 409
    assert (await client.patch(f"/api/usuarios/{owner['id']}", json={"rol": "Admin"})).status_code == 403
    assert (await client.patch(f"/api/usuarios/{owner['id']}/foto", files={"foto": ("x.png", b"invalid", "image/png")})).status_code == 422
    assert "/api/huertos/recomendar" not in module.app.openapi()["paths"]
    assert (await client.get("/health/live")).status_code == 200
