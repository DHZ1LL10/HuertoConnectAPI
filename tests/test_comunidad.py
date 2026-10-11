"""Community contracts with real JWT/session checks and isolated Mongo/ImageKit."""
import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bson import ObjectId
import httpx
from mongomock_motor import AsyncMongoMockClient
import pytest

from conftest import load_service
from test_integration import identity, picture

BASE = "/api/comunidad"
BODY = {"titulo": "Jitomate en maceta", "contenido": "Experiencia con drenaje y riego.", "region": "capital", "cultivo": "Jitomate"}


@pytest.fixture(scope="module")
def module():
    main = load_service("huertos-service")
    return SimpleNamespace(app=main.app, routes=importlib.import_module("app.routes.comunidad"),
                           service=importlib.import_module("app.services.comunidad"))


@pytest.fixture
async def api(module):
    db = AsyncMongoMockClient(tz_aware=True).community
    await module.service.init_indexes(db)
    owner, headers = await identity(db)
    other, foreign = await identity(db)
    admin, admin_headers = await identity(db)
    await db.usuarios.update_one({"_id": ObjectId(admin["id"])}, {"$set": {"role": "admin", "nombre": "Moderador"}})
    await db.usuarios.update_one({"_id": ObjectId(owner["id"])}, {"$set": {"nombre": "Agricultor", "apellidos": "Veracruz"}})
    module.app.state.mongodb = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test", headers=headers) as client:
        yield SimpleNamespace(client=client, db=db, owner=owner, other=other, foreign=foreign, admin=admin_headers, module=module)


async def create(api, body=None):
    response = await api.client.post(BASE + "/publicaciones", json=body or BODY)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_edit_delete_privacy_and_authorization(api):
    post = await create(api)
    pid = post["id"]
    assert post["region"] == "Capital" and post["autor"] == {"id": api.owner["id"], "nombre": "Agricultor Veracruz"}
    assert "email" not in post and "file_id" not in str(post)
    assert (await api.client.get(BASE + f"/publicaciones/{pid}", headers=api.foreign)).status_code == 200
    for headers in [api.foreign, api.admin]:
        assert (await api.client.patch(BASE + f"/publicaciones/{pid}", json={"titulo": "Intruso"}, headers=headers)).status_code == 403
        assert (await api.client.delete(BASE + f"/publicaciones/{pid}", headers=headers)).status_code == 403
    response = await api.client.patch(BASE + f"/publicaciones/{pid}", json={"titulo": "Mi experiencia", "region": "las montanas", "cultivo": None})
    assert response.status_code == 200 and response.json()["region"] == "Las Montañas" and response.json()["cultivo"] is None
    assert (await api.client.delete(BASE + f"/publicaciones/{pid}")).status_code == 200
    assert (await api.client.get(BASE + f"/publicaciones/{pid}")).status_code == 404
    assert (await api.client.get(BASE + "/publicaciones")).json()["items"] == []
    assert (await api.db.comunidad_publicaciones.find_one({"_id": ObjectId(pid)}))["deleted_at"]


@pytest.mark.parametrize("body", [
    {**BODY, "titulo": " "}, {**BODY, "contenido": " "}, {**BODY, "tipo": "Spam"},
    {**BODY, "region": "Costa inventada"}, {**BODY, "region": str(ObjectId())},
    {**BODY, "autor": {"id": "attacker"}}, {**BODY, "estado": "Publicada"}, {**BODY, "cultivo": " "},
])
async def test_invalid_or_injected_create(api, body):
    assert (await api.client.post(BASE + "/publicaciones", json=body)).status_code == 422


async def test_auth_revocation_validation_and_options(api):
    assert (await api.client.get(BASE + "/publicaciones", headers={"Authorization": ""})).status_code == 401
    options = (await api.client.get(BASE + "/opciones")).json()
    assert len(options["regiones"]) == 10 and options["max_fotos"] == 4
    for suffix in ["?limit=51", "?cursor=invalid", "?region=falsa", "?cultivo=%20"]:
        assert (await api.client.get(BASE + "/publicaciones" + suffix)).status_code == 422
    post = await create(api)
    for body, status in [({}, 400), ({"titulo": None}, 422), ({"estado": "Oculta"}, 422)]:
        assert (await api.client.patch(BASE + f"/publicaciones/{post['id']}", json=body)).status_code == status
    assert (await api.client.get(BASE + "/publicaciones/no-id")).status_code == 422
    await api.db.sesiones.update_many({"user_id": api.owner["id"]}, {"$set": {"activa": False}})
    assert (await api.client.get(BASE + "/publicaciones")).status_code == 401


async def test_cursor_filters_and_lightweight_list(api):
    first = await create(api)
    second = await create(api, {**BODY, "titulo": "Otra experiencia", "cultivo": "JÍTOMATE"})
    third = await create(api, {**BODY, "titulo": "Frijol", "region": "Olmeca", "cultivo": "Frijol", "tipo": "Consejo"})
    await api.db.comunidad_publicaciones.update_one({"_id": ObjectId(second["id"])}, {"$set": {"contenido": "x" * 5000, "fotos": [{"id": "photo", "url": "https://ik.imagekit.io/test/photo.png?tr=orig-true", "file_id": "private-id"}]}})
    result = (await api.client.get(BASE + "/publicaciones?limit=1")).json()
    assert result["items"][0]["id"] == third["id"] and result["hay_mas"]
    cursor = result["siguiente_cursor"]
    await api.db.comunidad_publicaciones.update_one({"_id": ObjectId(third["id"])}, {"$set": {"deleted_at": api.module.service.now()}})
    result = (await api.client.get(BASE + f"/publicaciones?limit=1&cursor={cursor}")).json()
    item = result["items"][0]
    assert item["id"] == second["id"] and len(item["resumen"]) == 240 and "contenido" not in item
    assert item["fotos"] == [] and item["total_fotos"] == 1 and "file_id" not in str(item)
    result = (await api.client.get(BASE + "/publicaciones?region=CAPITAL&cultivo=jitomate&incluir_fotos=true")).json()
    assert {i["id"] for i in result["items"]} == {first["id"], second["id"]}
    assert result["items"][0]["fotos"][0]["url"].endswith("orig-true")
    result = (await api.client.get(BASE + "/publicaciones?solo_mias=true", headers=api.foreign)).json()
    assert result["items"] == []


async def test_comments_counts_ownership_and_moderation(api):
    pid = (await create(api))["id"]
    url = BASE + f"/publicaciones/{pid}/comentarios"
    response = await api.client.post(url, json={"contenido": "Buena idea"}, headers=api.foreign)
    assert response.status_code == 201
    cid = response.json()["id"]
    assert (await api.client.get(url)).json()["items"][0]["autor"]["id"] == api.other["id"]
    assert (await api.client.get(BASE + f"/publicaciones/{pid}")).json()["total_comentarios"] == 1
    assert (await api.client.patch(BASE + f"/comentarios/{cid}", json={"contenido": "Robo"})).status_code == 403
    assert (await api.client.delete(BASE + f"/comentarios/{cid}")).status_code == 403
    assert (await api.client.patch(BASE + f"/comentarios/{cid}", json={"contenido": "Nueva idea"}, headers=api.foreign)).status_code == 200
    response = await api.client.patch(BASE + f"/comentarios/{cid}/moderacion", json={"estado": "Oculta", "motivo": "Contenido inapropiado"}, headers=api.admin)
    assert response.status_code == 200
    assert (await api.client.get(url)).json()["items"] == []
    assert (await api.client.get(BASE + f"/publicaciones/{pid}")).json()["total_comentarios"] == 0
    assert (await api.client.get(url + "?incluir_ocultos=true")).status_code == 403
    assert len((await api.client.get(url + "?incluir_ocultos=true", headers=api.admin)).json()["items"]) == 1
    assert (await api.client.delete(BASE + f"/comentarios/{cid}", headers=api.foreign)).status_code == 200


async def test_hidden_posts_and_deleted_parent_are_not_accessible(api):
    pid = (await create(api))["id"]
    moderation = BASE + f"/publicaciones/{pid}/moderacion"
    body = {"estado": "Oculta", "motivo": "Revisión de contenido"}
    assert (await api.client.patch(moderation, json=body)).status_code == 403
    assert (await api.client.patch(moderation, json=body, headers=api.foreign)).status_code == 403
    assert (await api.client.patch(moderation, json=body, headers=api.admin)).status_code == 200
    assert (await api.client.get(BASE + "/publicaciones")).json()["items"] == []
    assert (await api.client.get(BASE + "/publicaciones?incluir_ocultas=true")).status_code == 403
    assert len((await api.client.get(BASE + "/publicaciones?solo_mias=true&incluir_ocultas=true")).json()["items"]) == 1
    assert len((await api.client.get(BASE + "/publicaciones?incluir_ocultas=true", headers=api.admin)).json()["items"]) == 1
    assert (await api.client.get(BASE + f"/publicaciones/{pid}", headers=api.foreign)).status_code == 404
    assert (await api.client.get(BASE + f"/publicaciones/{pid}")).status_code == 200
    assert (await api.client.patch(BASE + f"/publicaciones/{pid}", json={"titulo": "Cambio"})).status_code == 404
    for headers in [None, api.foreign, api.admin]:
        assert (await api.client.post(BASE + f"/publicaciones/{pid}/comentarios", json={"contenido": "No visible"}, headers=headers)).status_code == 404
        assert (await api.client.put(BASE + f"/publicaciones/{pid}/me-gusta", headers=headers)).status_code == 404
    assert (await api.client.patch(moderation, json={**body, "estado": "Publicada"}, headers=api.admin)).status_code == 200
    doc = await api.db.comunidad_publicaciones.find_one({"_id": ObjectId(pid)})
    assert len(doc["moderacion"]) == 2 and doc["moderacion"][0]["moderado_por"]
    assert (await api.client.delete(BASE + f"/publicaciones/{pid}")).status_code == 200
    assert (await api.client.get(BASE + f"/publicaciones/{pid}/comentarios", headers=api.admin)).status_code == 404
    assert (await api.client.patch(moderation, json=body, headers=api.admin)).status_code == 404


async def test_likes_are_unique_idempotent_and_not_spoofable(api):
    pid = (await create(api))["id"]
    url = BASE + f"/publicaciones/{pid}/me-gusta"
    responses = await asyncio.gather(*(api.client.put(url) for _ in range(4)))
    assert all(r.status_code == 200 and r.json()["total_me_gusta"] == 1 for r in responses)
    assert (await api.client.put(url, headers=api.foreign)).json()["total_me_gusta"] == 2
    post = (await api.client.get(BASE + f"/publicaciones/{pid}")).json()
    assert post["me_gusta"] and post["total_me_gusta"] == 2
    for _ in range(2):
        response = await api.client.delete(url)
        assert response.json()["total_me_gusta"] == 1 and response.json()["me_gusta"] is False


async def test_photos_preserve_bytes_limits_and_permissions(api, monkeypatch):
    pid = (await create(api))["id"]
    upload = AsyncMock(return_value={"secure_url": "https://ik.imagekit.io/test/plant.png?tr=orig-true", "public_id": "file-id"})
    monkeypatch.setattr(api.module.routes, "upload_image", upload)
    url = BASE + f"/publicaciones/{pid}/fotos"
    original = picture()
    assert (await api.client.post(url, files={"foto": original}, headers=api.foreign)).status_code == 403
    upload.assert_not_called()
    response = await api.client.post(url, files={"foto": original})
    assert response.status_code == 201 and response.json()["url"].endswith("tr=orig-true")
    assert upload.call_args.args[0] == original[1]
    assert "file_id" not in response.text
    for _ in range(3):
        assert (await api.client.post(url, files={"foto": original})).status_code == 201
    assert (await api.client.post(url, files={"foto": original})).status_code == 409
    assert upload.call_count == 4


@pytest.mark.parametrize("file,status", [
    (("x.txt", b"invalid", "text/plain"), 415), (("x.png", b"invalid", "image/png"), 422),
    (("x.png", b"x" * (5 * 1024 * 1024 + 1), "image/png"), 413),
])
async def test_invalid_photos(api, file, status, monkeypatch):
    pid = (await create(api))["id"]
    upload = AsyncMock()
    monkeypatch.setattr(api.module.routes, "upload_image", upload)
    assert (await api.client.post(BASE + f"/publicaciones/{pid}/fotos", files={"foto": file})).status_code == status
    upload.assert_not_called()


async def test_upload_failure_and_concurrent_rollback(api, monkeypatch):
    pid = (await create(api))["id"]
    url = BASE + f"/publicaciones/{pid}/fotos"
    monkeypatch.setattr(api.module.routes, "upload_image", AsyncMock(side_effect=RuntimeError("private-key-must-not-leak")))
    response = await api.client.post(url, files={"foto": picture()})
    assert response.status_code == 503 and "private-key" not in response.text
    async def upload_and_hide(data, **kwargs):
        await api.db.comunidad_publicaciones.update_one({"_id": ObjectId(pid)}, {"$set": {"estado": "Oculta"}})
        return {"secure_url": "https://ik.imagekit.io/test/a.png", "public_id": "created-only"}
    monkeypatch.setattr(api.module.routes, "upload_image", upload_and_hide)
    remove = AsyncMock()
    monkeypatch.setattr(api.module.routes, "delete_image", remove)
    response = await api.client.post(url, files={"foto": picture()})
    assert response.status_code == 409
    remove.assert_awaited_once_with("created-only")


async def test_post_rate_limit(api):
    for _ in range(5):
        await create(api)
    response = await api.client.post(BASE + "/publicaciones", json=BODY)
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"


async def test_comment_rate_limit(api):
    pid = (await create(api))["id"]
    url = BASE + f"/publicaciones/{pid}/comentarios"
    for _ in range(20):
        assert (await api.client.post(url, json={"contenido": "Idea"})).status_code == 201
    assert (await api.client.post(url, json={"contenido": "Idea"})).status_code == 429


async def test_moderation_audit_is_admin_only_and_bounded(api):
    pid = (await create(api))["id"]
    history = BASE + f"/moderacion/publicaciones/{pid}"
    assert (await api.client.get(history)).status_code == 403
    for index in range(22):
        response = await api.client.patch(BASE + f"/publicaciones/{pid}/moderacion", headers=api.admin,
                                         json={"estado": "Publicada", "motivo": f"Revisión de prueba {index}"})
        assert response.status_code == 200
    result = (await api.client.get(history, headers=api.admin)).json()
    assert len(result["historial"]) == 20 and result["historial"][0]["motivo"] == "Revisión de prueba 2"
    assert (await api.client.get(BASE + f"/moderacion/usuarios/{pid}", headers=api.admin)).status_code == 422


def test_openapi_upload_and_jwt_contract(module):
    spec = module.app.openapi()
    route = spec["paths"][BASE + "/publicaciones/{publicacion_id}/fotos"]["post"]
    assert route["security"] == [{"HTTPBearer": []}]
    media = route["requestBody"]["content"]["multipart/form-data"]["schema"]
    upload_schema = spec["components"]["schemas"][media["$ref"].split("/")[-1]]
    assert upload_schema["properties"]["foto"]["format"] == "binary"
    for path, methods in spec["paths"].items():
        if not path.startswith(BASE):
            continue
        for operation in methods.values():
            assert len(operation["tags"]) == 1, (path, operation["tags"])
    create_post = spec["paths"][BASE + "/publicaciones"]["post"]
    assert create_post["summary"].startswith("Crear publicación")
    assert not create_post.get("parameters")


async def test_gateway_routes_and_unified_swagger(module):
    spec = module.app.openapi()
    gateway = load_service("gateway")
    def handler(request):
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=spec if request.url.host == "huertos-service" else {"paths": {}})
        assert request.url.host == "huertos-service" and request.url.path == BASE + "/opciones"
        assert request.headers["authorization"] == "Bearer sample"
        return httpx.Response(200, json={"community": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        gateway._http_client = upstream
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app), base_url="http://test") as client:
            response = await client.get(BASE + "/opciones", headers={"Authorization": "Bearer sample"})
            assert response.status_code == 200
            unified = (await client.get("/openapi.json")).json()
            operation = unified["paths"][BASE + "/publicaciones"]["post"]
            assert operation["security"] == [{"HTTPBearer": []}]
            assert operation["tags"] == ["Huertos Service — Comunidad — Publicaciones"]
