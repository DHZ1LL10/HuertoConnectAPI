"""Bounded dependency probes, without exposing connection details."""
import asyncio
from fastapi.responses import JSONResponse


async def dependency_readiness(db, agent_client=None):
    checks = {"mongodb": False}
    try:
        async with asyncio.timeout(5):
            await db.command("ping")
        checks["mongodb"] = True
    except Exception:
        pass
    if agent_client is not None:
        checks["agent"] = False
        try:
            async with asyncio.timeout(5):
                response = await agent_client.get("/health/ready", timeout=4)
                checks["agent"] = response.status_code == 200
        except Exception:
            pass
    ok = all(checks.values())
    return JSONResponse({"status": "ok" if ok else "unavailable", "dependencies": checks}, status_code=200 if ok else 503)
