from urllib.parse import quote

from shared.regions import VERACRUZ_REGIONS, seed_regions
from test_huertos_service import api, module


async def test_official_catalog_and_name_lookup(api):
    client, db, owner, other, foreign = api
    await seed_regions(db)
    await seed_regions(db)
    await db.regiones.insert_one({"nombre": "Bajio Norte"})
    result = await client.get("/api/regiones")
    assert {r["nombre"] for r in result.json()} == set(VERACRUZ_REGIONS)
    assert (await client.get("/api/regiones/Capital")).status_code == 200
    assert (await client.get("/api/regiones/las%20montanas")).json()["nombre"] == "Las Montañas"
    assert (await client.get("/api/regiones/no-existe")).status_code == 404
    assert (await client.post("/api/regiones", json={"nombre": "Bajio Norte"})).status_code == 422


async def test_huerto_by_region_name(api):
    client, db, owner, other, foreign = api
    await seed_regions(db)
    created = await client.post("/api/huertos", json={"nombre": "Xalapa", "region": "capital"})
    assert created.status_code == 201, created.text
    assert created.json()["region"] == "Capital"
    hid = created.json()["id"]
    assert len((await client.get("/api/huertos?region=Capital")).json()) == 1
    updated = await client.put(f"/api/huertos/{hid}", json={"region": "Las Montañas"})
    assert updated.json()["region"] == "Las Montañas"
    assert (await client.get("/api/huertos?region=Capital")).json() == []
    assert (await client.get("/api/huertos?region=Capital", headers=foreign)).json() == []


async def test_admin_user_region_name(api):
    from bson import ObjectId
    client, db, owner, other, foreign = api
    await seed_regions(db)
    await db.usuarios.update_one({"_id": ObjectId(owner["id"])}, {"$set": {"rol": "Admin"}})
    response = await client.patch(f"/api/usuarios/{owner['id']}", json={"region": "Papaloapan"})
    assert response.status_code == 200, response.text
    assert response.json()["region"] == "Papaloapan"
