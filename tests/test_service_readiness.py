import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from conftest import load_service
from shared.readiness import dependency_readiness


@pytest.mark.asyncio
@pytest.mark.parametrize("mongo_ok,agent_ok", [(True, True), (False, True), (True, False)])
async def test_chat_dependencies(mongo_ok, agent_ok):
    db = SimpleNamespace(command=AsyncMock(side_effect=None if mongo_ok else RuntimeError("private")))
    agent = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200 if agent_ok else 503)))
    result = await dependency_readiness(db, agent)
    assert result.status_code == (200 if mongo_ok and agent_ok else 503)
    assert json.loads(result.body)["dependencies"] == {"mongodb": mongo_ok, "agent": agent_ok}
    assert b"private" not in result.body


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [None, "plagas-service", "agent-service"])
async def test_gateway_checks_readiness_and_propagates_failure(failed):
    module = load_service("gateway")
    def respond(request):
        assert request.url.path == "/health/ready"
        return httpx.Response(503 if request.url.host == failed else 200)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        module._http_client = client
        result = await module.gateway_health()
    assert result.status_code == (503 if failed else 200)
    assert json.loads(result.body)["status"] == ("degraded" if failed else "ok")
