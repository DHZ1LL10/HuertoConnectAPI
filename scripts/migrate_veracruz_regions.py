"""Explicit catalog replacement: backup old regions and detach invalid references, never guess geography."""
import asyncio
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.motor_asyncio import AsyncIOMotorClient
from shared.config import settings
from shared.regions import VERACRUZ_REGIONS, region_key, seed_regions


async def migrate():
    client = AsyncIOMotorClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        db = client[settings.MONGO_DB]
        await client.admin.command("ping")
        old = await db.regiones.find({}).to_list(None)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = client[db.name + "_regions_backup_" + stamp]
        if old:
            await backup.regiones.insert_many(old)
        await seed_regions(db)
        canonical = {r["nombre"]: r for r in await db.regiones.find({"nombre": {"$in": list(VERACRUZ_REGIONS)}}).to_list(None)}
        affected = 0
        for region in old:
            name = region.get("nombre", "")
            key = region_key(name)
            key = {"montanas": "las montanas", "totonacapan": "totonaca"}.get(key, key)
            target = next((r for n, r in canonical.items() if region_key(n) == key), None)
            for collection in ("huertos", "usuarios"):
                query = {"region_id": {"$in": [region["_id"], str(region["_id"])]}}
                docs = await db[collection].find(query).to_list(None)
                if docs:
                    await backup[collection].insert_many(docs)
                if target:
                    update = {"$set": {"region_id": str(target["_id"]), "region": target["nombre"]}}
                else:
                    update = {"$set": {"region_id": None, "region": None, "region_anterior": name}}
                affected += (await db[collection].update_many(query, update)).modified_count
            if name not in VERACRUZ_REGIONS:
                await db.regiones.delete_one({"_id": region["_id"]})
        print({"regiones": await db.regiones.count_documents({}), "referencias_actualizadas": affected,
               "respaldo": backup.name, "nota": "Las regiones no reconocidas quedan sin asignar, con region_anterior conservada."})
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
