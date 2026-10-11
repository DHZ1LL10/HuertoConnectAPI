# Agent Service

Servicio interno Python/FastAPI en puerto 8006 para generación con Ollama.
El modelo predeterminado es `gemma3:1b`. Chat valida sesiones y conserva el
historial en MongoDB; Agent no mantiene una segunda base de conversaciones.

Contrato completo: [Chat y asistente](../docs/DOCUMENTACION_API.md#8-chat-y-asistente-agrícola).

```powershell
docker compose up -d --build
python -m pytest tests/test_agent_service.py tests/test_agent_chat_bridge.py -q
python scripts/smoke_agent.py --generate
```

El acceso interno requiere `X-API-Key` y `X-User-ID`; esas claves no se envían al
cliente. El endpoint público es `POST /api/agent/v1/chat` con JWT de la API.
