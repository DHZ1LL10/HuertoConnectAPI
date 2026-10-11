"""Bounded asynchronous Ollama transport. No model downloads or fake responses."""
import asyncio
import json
import logging
import httpx
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger("huerto.agent.ollama")


class OllamaError(RuntimeError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaUnavailableError(OllamaError):
    pass


class OllamaProvider:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.model = settings.ollama_model
        self.client = client or httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.ollama_timeout_seconds, connect=5, pool=2),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            trust_env=False,
        )

    async def close(self):
        await self.client.aclose()

    async def warm(self):
        """Load the existing model before accepting traffic; never download it."""
        try:
            async with asyncio.timeout(self.settings.ollama_timeout_seconds):
                response = await self.client.post("/api/generate", json={
                    "model": self.model, "stream": False,
                    "keep_alive": self.settings.ollama_keep_alive,
                    "options": {"num_ctx": self.settings.ollama_context_window},
                })
                response.raise_for_status()
        except (httpx.HTTPError, TimeoutError):
            logger.warning("model_warmup_failed")

    async def health(self):
        try:
            async with asyncio.timeout(self.settings.ollama_health_timeout_seconds):
                response = await self.client.get("/api/tags", timeout=self.settings.ollama_health_timeout_seconds)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                    return False
                names = {item.get("name") for item in data["models"] if isinstance(item, dict) and isinstance(item.get("name"), str)}
                expected = self.model if ":" in self.model else self.model + ":latest"
                return expected in names or self.model in names
        except (httpx.HTTPError, ValueError, TimeoutError):
            return False

    async def chat(self, message, history):
        body = {
            "model": self.model, "stream": False,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": message}],
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
                "num_ctx": self.settings.ollama_context_window,
                "num_predict": self.settings.ollama_max_output_tokens,
            },
            "keep_alive": self.settings.ollama_keep_alive,
        }
        try:
            async with asyncio.timeout(self.settings.ollama_timeout_seconds):
                async with self.client.stream("POST", "/api/chat", json=body) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 262144:
                            raise OllamaUnavailableError("Respuesta del proveedor demasiado grande")
            data = json.loads(content)
            if isinstance(data, dict):
                logger.info("generation_metrics model=%s load_ms=%.1f prompt_ms=%.1f generation_ms=%.1f tokens=%s",
                            self.model, data.get("load_duration", 0) / 1e6,
                            data.get("prompt_eval_duration", 0) / 1e6,
                            data.get("eval_duration", 0) / 1e6, data.get("eval_count", 0))
            if not isinstance(data, dict) or data.get("done") is not True:
                raise OllamaUnavailableError("Respuesta incompleta del proveedor")
            result = data.get("message")
            answer = result.get("content") if isinstance(result, dict) else None
            if not isinstance(answer, str) or not answer.strip():
                raise OllamaUnavailableError("Respuesta vacía o inválida del proveedor")
            model = data.get("model") or self.model
            if not isinstance(model, str):
                raise OllamaUnavailableError("Modelo inválido en la respuesta")
            return answer.strip(), model
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise OllamaTimeoutError("Ollama excedió el tiempo de respuesta") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailableError("No fue posible obtener una respuesta de Ollama") from exc
