"""Real ASGI Chat-to-Agent contract; only MongoDB and Ollama are isolated."""
from bson import ObjectId
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient
from conftest import load_service
from shared.auth.dependencies import get_current_user
from test_agent_service import Provider, KEY


@pytest.mark.parametrize("failure", [None, "unavailable", "timeout", "busy"])
async def test_chat_agent_history_ownership_and_failures(failure):
    agent_module = load_service("agent-service")
    provider = Provider()
    agent = agent_module.create_app(agent_module.Settings(_env_file=None, app_api_key=KEY), provider)
    chat = load_service("chat-service").app
    db = AsyncMongoMockClient(tz_aware=True).bridge
    chat.state.mongodb = db
    user = {"id": str(ObjectId()), "rol": "Usuario"}
    chat.dependency_overrides[get_current_user] = lambda: user
    cid = str((await db.chat_conversaciones.insert_one({"usuario_id": user["id"], "estado": "Activa"})).inserted_id)
    async with agent.router.lifespan_context(agent):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=agent), base_url="http://testserver") as upstream:
            chat.state.agent_client = upstream
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=chat), base_url="http://testserver") as client:
                body = {"message": "¿Cómo riego mis plantas de jitomate?", "conversation_id": cid}
                response = await client.post("/api/agent/v1/chat", json=body)
                assert response.status_code == 200, response.text
                assert response.json()["conversation_id"] == cid
                assert await db.chat_mensajes.count_documents({}) == 2
                if failure == "unavailable":
                    provider.error = agent_module.OllamaUnavailableError("private upstream detail")
                elif failure == "timeout":
                    provider.error = agent_module.OllamaTimeoutError("private upstream detail")
                elif failure == "busy":
                    agent.state.generator.settings.queue_timeout_seconds = 0.01
                    await agent.state.generator.slots.acquire()
                response = await client.post("/api/agent/v1/chat", json=body)
                assert response.status_code == {None: 200, "unavailable": 503, "timeout": 504, "busy": 429}[failure], response.text
                assert "private upstream" not in response.text
                assert await db.chat_mensajes.count_documents({}) == (2 if failure else 4)
                assert "busy_until" not in await db.chat_conversaciones.find_one({"_id": ObjectId(cid)})
                if failure != "busy":
                    assert [m["role"] for m in provider.calls[-1][1]] == ["user", "assistant"]
                else:
                    agent.state.generator.slots.release()
                user["id"] = str(ObjectId())
                calls = len(provider.calls)
                assert (await client.post("/api/agent/v1/chat", json=body)).status_code == 404
                assert (await client.get(f"/api/agent/v1/conversations/{cid}/messages")).status_code == 404
                assert len(provider.calls) == calls
    chat.dependency_overrides.clear()
