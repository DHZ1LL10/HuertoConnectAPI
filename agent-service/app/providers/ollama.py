from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.prompts import SYSTEM_PROMPT


class OllamaError(RuntimeError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaUnavailableError(OllamaError):
    pass


class OllamaProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.ollama_model
        self.client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.ollama_timeout_seconds),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def health(self) -> bool:
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            names = {item.get("name") for item in models if isinstance(item, dict)}
            # Ollama puede devolver el modelo con o sin sufijo latest.
            return self.model in names or f"{self.model}:latest" in names or any(
                isinstance(name, str) and name.startswith(self.model + ":") for name in names
            )
        except (httpx.HTTPError, ValueError):
            return False

    async def chat(self, message: str, history: list[dict[str, str]]) -> tuple[str, str]:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": message},
            ],
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
                "num_ctx": self.settings.ollama_context_window,
                "num_predict": self.settings.ollama_max_output_tokens,
            },
            "keep_alive": self.settings.ollama_keep_alive,
        }

        try:
            response = await self.client.post("/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
            answer = data.get("message", {}).get("content", "").strip()
            if not answer:
                raise OllamaUnavailableError("Ollama devolvió una respuesta vacía")
            return answer, data.get("model") or self.model
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama excedió el tiempo de respuesta") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise OllamaUnavailableError(f"Ollama respondió con error: {detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailableError("No fue posible comunicarse con Ollama") from exc
