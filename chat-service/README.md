# Chat Service

Servicio Python/FastAPI en puerto 8004 con MongoDB. Conserva conversaciones
y mensajes por usuario y coordina la generación mediante Agent.

Contrato completo: [Chat y asistente](../docs/DOCUMENTACION_API.md#8-chat-y-asistente-agrícola).

```powershell
docker compose up -d --build chat-service
python -m pytest tests/test_agent_chat_bridge.py tests/test_integration.py -q
```

La ruta pública de generación es `POST /api/agent/v1/chat`.
El usuario no puede leer ni escribir en conversaciones de otra cuenta.
