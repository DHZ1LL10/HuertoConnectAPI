import importlib
import io
import csv
from datetime import datetime, timezone
from types import SimpleNamespace
import httpx
import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from conftest import load_service
from shared.sql_ownership import restrict_session
from test_integration import identity


@pytest.fixture(scope="module")
def module():
    return load_service("reportes-service")


@pytest.fixture
async def api(module):
    db = AsyncMongoMockClient(tz_aware=True).reportes
    user, headers = await identity(db)
    other, foreign = await identity(db)
    hid = str((await db.huertos.insert_one({"nombre": "Huerto <prueba> & café", "municipio": "Xalapa", "usuario_id": user["id"]})).inserted_id)
    for day, detected in [(1, True), (2, False), (3, True)]:
        await db.diagnosticos.insert_one({"huerto_id": hid, "usuario_id": user["id"], "fecha": datetime(2026, 9, day, tzinfo=timezone.utc), "tipo": "plaga", "clase": "pulgones", "confianza": .91, "detectado": detected, "modelo": "yolo_plagas_veracruz_v6", "version": "v6"})
    module.app.state.mongodb = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test", headers=headers) as client:
        yield client, db, hid, foreign


@pytest.mark.parametrize("format", ["pdf", "csv"])
async def test_export_ownership_and_history(api, format):
    client, db, hid, foreign = api
    response = await client.get(f"/api/reportes/huertos/{hid}/{format}")
    assert response.status_code == 200, response.text[:100]
    assert response.headers["x-report-total"] == "3"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-report-truncated"] == "false"
    assert response.content.startswith(b"%PDF" if format == "pdf" else b"\xef\xbb\xbf")
    assert (await client.get(f"/api/reportes/huertos/{hid}/{format}", headers=foreign)).status_code == 404
    assert (await client.get(f"/api/reportes/huertos/{hid}/{format}", headers={"Authorization": ""})).status_code == 401
    assert await db.reporte_exportaciones.count_documents({}) == 1


async def test_dates_statistics_and_truncation(api):
    client, db, hid, foreign = api
    route = f"/api/reportes/huertos/{hid}"
    response = await client.get(route + "/csv?limite=1")
    assert response.headers["x-report-truncated"] == "true"
    assert response.headers["x-report-records"] == "1"
    assert len(list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))) == 2
    stats = await client.get(route + "/estadisticas/resumen?desde=2026-09-02&hasta=2026-09-02")
    assert stats.json() == {"huerto_id": hid, "total": 1, "detectados": 0, "no_detectados": 1}
    assert (await client.get(route + "/csv?desde=2026-09-04&hasta=2026-09-01")).status_code == 422
    assert (await client.get(route + "/csv?limite=1001")).status_code == 422
    assert (await client.get(route + "/csv?desde=invalid")).status_code == 422
    assert (await client.get(route + "/estadisticas/resumen", headers=foreign)).status_code == 404
    await db.huertos.update_one({"_id": ObjectId(hid)}, {"$set": {"deleted_at": datetime.now(timezone.utc)}})
    assert (await client.get(route + "/pdf")).status_code == 404


@pytest.mark.parametrize("value", ["=1+1", " +SUM(A1)", "@cmd", "\tformula", "\rformula", "\nformula", "-2+3"])
def test_csv_formula_escaping(module, value):
    renderer = importlib.import_module("app.export")
    assert renderer.safe_cell(value).startswith("'")


def test_pdf_multipage_and_empty(module):
    import fitz
    renderer = importlib.import_module("app.export")
    for count in (0, 70):
        data, _ = renderer.render_report({"nombre": "Café & cítricos <Veracruz>"}, [{"clase": "pulgones", "modelo": "yolo_plagas_veracruz_v6", "nota": "Validar con especialista", "confianza": .9}] * count, "pdf")
        with fitz.open(stream=data, filetype="pdf") as document:
            text = "".join(page.get_text() for page in document)
            assert "Café & cítricos <Veracruz>" in text
            assert (len(document) > 1) == (count > 0)
            assert "Página 1" in text
            if count == 0:
                assert "Sin diagnósticos" in text


def test_schema_and_sql_ownership(module):
    for body in ({"nombre": " " , "tipo": "csv"}, {"nombre": "x", "tipo": "pdf", "generado_por": "intruso"}, {"nombre": "x", "tipo": "pdf", "archivo_url": "javascript:alert(1)"}):
        with pytest.raises(ValueError):
            module.ReporteCreate(**body)
    engine = create_engine("sqlite://")
    module.Reporte.__table__.create(engine)
    with Session(engine) as session:
        session.add_all([module.Reporte(nombre="own", tipo="pdf", generado_por="own"), module.Reporte(nombre="foreign", tipo="pdf", generado_por="foreign")])
        session.commit()
    with Session(engine) as session:
        restrict_session(SimpleNamespace(sync_session=session), [(module.Reporte, "generado_por", ["own"])])
        assert [r.nombre for r in session.scalars(select(module.Reporte))] == ["own"]
    engine.dispose()


@pytest.mark.parametrize("url,expected", [(None, "En_proceso"), ("https://example.com/reporte.pdf", "Generado")])
async def test_create_report_matches_initial_sql_constraint(module, url, expected):
    import re
    from pathlib import Path
    from unittest.mock import AsyncMock, Mock
    sql = (Path(__file__).resolve().parents[1] / "scripts/init-postgres.sql").read_text(encoding="utf-8")
    report_sql = sql.split("CREATE TABLE reportes (")[1].split("CREATE TABLE auditoria_logs")[0]
    allowed = re.search(r"CHECK \(estado IN \((.*?)\)\)", report_sql).group(1)
    states = re.findall(r"'([^']+)'", allowed)
    db = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
    result = await module.create_reporte(module.ReporteCreate(nombre="Reporte", tipo="pdf", archivo_url=url), db, {"id": "owner"})
    assert result.estado == expected
    assert result.estado in states
