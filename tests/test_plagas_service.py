import importlib
import io
from types import SimpleNamespace
import httpx
import pytest
from unittest.mock import AsyncMock
from PIL import Image
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from fastapi import HTTPException
from conftest import load_service
from shared.database import Base
from shared.sql_ownership import restrict_session
from test_integration import identity, FakeClassifier


def test_swagger_image_forms(module):
    spec = module.app.openapi()
    for removed in ("/api/modelos", "/api/plagas", "/api/predicciones", "/api/recomendaciones"):
        assert removed not in spec["paths"]
    assert "/ai/rendimiento/opciones" in spec["paths"]
    for path in ("/ai/plagas/predict", "/ai/enfermedades/predict", "/api/plagas/detectar"):
        operation = spec["paths"][path]["post"]
        assert not operation.get("deprecated", False)
        content = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
        schema = spec["components"]["schemas"][content["$ref"].split("/")[-1]]
        assert schema["properties"]["imagen"]["type"] == "string"
        assert schema["properties"]["imagen"]["format"] == "binary"
        assert "guardar_imagen" in schema["properties"]


async def test_prediction_stores_imagekit_url(api, monkeypatch):
    client, db, manager, hid, foreign = api
    from shared.services import image_storage
    upload = AsyncMock(return_value={"secure_url": "https://ik.imagekit.io/test/foto.png", "public_id": "image-id"})
    monkeypatch.setattr(image_storage, "upload_image", upload)
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), "green").save(stream, format="PNG")
    files = {"imagen": ("foto.png", stream.getvalue(), "image/png")}
    response = await client.post("/ai/enfermedades/predict", files=files, data={"huerto_id": hid, "guardar_imagen": "true"})
    assert response.status_code == 200, response.text
    assert response.json()["imagen_file_id"] == "image-id"
    stored = await db.diagnosticos.find_one({"huerto_id": hid})
    assert stored["imagen_url"] == "https://ik.imagekit.io/test/foto.png"
    upload.assert_awaited_once()


@pytest.fixture(scope="module")
def module():
    # Service modules use the same Base in this multi-service test process.
    Base.metadata.clear()
    return load_service("plagas-service")


@pytest.fixture
async def api(module):
    db = AsyncMongoMockClient(tz_aware=True).plagas
    owner, headers = await identity(db)
    other, other_headers = await identity(db)
    hid = str((await db.huertos.insert_one({"usuario_id": owner["id"]})).inserted_id)
    manager = module.ModelManager()
    manager.models = {"plaga": FakeClassifier(), "enfermedad": FakeClassifier()}
    manager.metadata = {"plaga": {"version": "test"}, "enfermedad": {"version": "test"}}
    module.app.state.models = manager
    module.app.state.mongodb = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test", headers=headers) as client:
        yield client, db, manager, hid, other_headers


def photo(fmt="PNG", mime="image/png"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(stream, format=fmt)
    return {"imagen": ("plant." + fmt.lower(), stream.getvalue(), mime)}


@pytest.mark.parametrize("endpoint", ["/ai/plagas/predict", "/ai/enfermedades/predict", "/api/plagas/detectar"])
async def test_classification_and_history(api, endpoint):
    client, db, manager, hid, other = api
    response = await client.post(endpoint, files=photo(), data={"huerto_id": hid})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["recomendaciones"]
    assert result["detectado"] and result["clase"] == "pulgones"
    assert len(result["top"]) == 3 and result["confianza"] == .9
    assert not ({"boxes", "x1", "y1", "x2", "y2"} & result.keys())
    assert result["diagnostico_id"]
    history = await client.get(f"/ai/diagnosticos/{hid}")
    assert len(history.json()) == 1
    assert (await client.get(f"/ai/diagnosticos/{hid}", headers=other)).status_code == 404
    assert (await client.post(endpoint, files=photo(), data={"huerto_id": hid}, headers=other)).status_code == 404
    assert await db.diagnosticos.count_documents({}) == 1


@pytest.mark.parametrize("fmt,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
async def test_formats(api, fmt, mime):
    assert (await api[0].post("/ai/plagas/predict", files=photo(fmt, mime))).status_code == 200


async def test_invalid_uploads_and_auth(api, monkeypatch):
    client, db, manager, hid, other = api
    assert (await client.post("/ai/plagas/predict", files=photo(), headers={"Authorization": ""})).status_code == 401
    for files, status in [({"imagen": ("x.png", b"bad", "image/png")}, 422), (photo("PNG", "image/jpeg"), 422), (photo("PNG", "text/plain"), 415)]:
        assert (await client.post("/ai/plagas/predict", files=files)).status_code == status
    routes = importlib.import_module("app.routes.ai")
    monkeypatch.setattr(routes.settings, "AI_MAX_IMAGE_BYTES", 10)
    assert (await client.post("/ai/plagas/predict", files=photo())).status_code == 413
    assert await db.diagnosticos.count_documents({}) == 0


@pytest.mark.parametrize("values,detected", [((.7,.2,.1), True), ((.69,.2,.11), False), ((.5,.4,.1), False)])
async def test_thresholds(api, values, detected):
    client, db, manager, hid, other = api
    manager.models["plaga"] = FakeClassifier(values)
    result = (await client.post("/ai/plagas/predict", files=photo())).json()
    assert result["detectado"] is detected
    if not detected:
        assert result["clase"] == "No detectada / no soportada"


async def test_missing_busy_and_invalid_model(api):
    client, db, manager, hid, other = api
    assert (await client.get("/ai/plagas/classes")).json()["clases"]["0"] == "pulgones"
    manager.locks["plaga"].acquire()
    try:
        assert (await client.post("/ai/plagas/predict", files=photo())).status_code == 429
    finally:
        manager.locks["plaga"].release()
    manager.models["plaga"] = FakeClassifier((.9,.9,.9))
    assert (await client.post("/ai/plagas/predict", files=photo())).status_code == 503
    manager.models.pop("plaga")
    assert (await client.post("/ai/plagas/predict", files=photo())).status_code == 503
    assert (await client.get("/ai/plagas/classes")).status_code == 503
    assert (await client.get("/ai/health")).status_code == 503


def test_uuid_and_schema_validation(module):
    routes = importlib.import_module("app.routes.routes")
    schemas = importlib.import_module("app.models.schemas")
    with pytest.raises(HTTPException) as error:
        routes.parse_uuid("not-a-uuid")
    assert error.value.status_code == 422
    for body in ({"confianza": -1}, {"confianza": 101}, {"estado": "unknown"}, {"severidad": "unknown"}):
        with pytest.raises(ValueError):
            schemas.PlagaDeteccionUpdate(**body)


async def test_hlb_dynamic_classes_and_body_limit(api):
    client, db, manager, hid, other = api
    model = FakeClassifier((.9, .1))
    model.names = {0: "hlb", 1: "otra_clase"}
    manager.models["enfermedad"] = model
    result = (await client.post("/ai/enfermedades/predict", files=photo())).json()
    assert len(result["top"]) == 2
    assert "compatibles con HLB" in result["nota"]
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == 503
    assert (await client.post("/ai/plagas/predict", content=b"x" * (manager.config.AI_MAX_IMAGE_BYTES + 65537))).status_code == 413


def test_missing_models_and_idempotent_loading(module, tmp_path):
    manager = module.ModelManager()
    manager.paths = {k: tmp_path / f"{k}.missing" for k in manager.paths}
    manager.load()
    assert not manager.models
    assert all(not m["loaded"] for m in manager.health().values())
    manager.models["plaga"] = sentinel = object()
    manager.load()
    assert manager.models["plaga"] is sentinel


def test_sql_ownership_including_recommendations(module):
    models = importlib.import_module("app.models.models")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    policies = (models.PlagaDeteccion, models.Alerta, models.Prediccion, models.RecomendacionCultivo)
    with Session(engine) as session:
        own = models.RecomendacionCultivo(huerto_id="own", tipo_recomendacion="riego", descripcion="own")
        foreign = models.RecomendacionCultivo(huerto_id="foreign", tipo_recomendacion="riego", descripcion="foreign")
        session.add_all([own, foreign])
        session.commit()
        foreign_id = foreign.id
    with Session(engine) as session:
        restrict_session(SimpleNamespace(sync_session=session), [(m, "huerto_id", ["own"]) for m in policies])
        assert [r.descripcion for r in session.scalars(select(models.RecomendacionCultivo))] == ["own"]
        assert session.execute(delete(models.RecomendacionCultivo).where(models.RecomendacionCultivo.id == foreign_id)).rowcount == 0
        session.add(models.RecomendacionCultivo(huerto_id="foreign", tipo_recomendacion="riego", descripcion="attack"))
        with pytest.raises(HTTPException):
            session.flush()
        session.rollback()
    engine.dispose()
