"""Stateless response generation; Chat supplies and owns conversation history."""
import asyncio
from app.providers.ollama import OllamaTimeoutError
from app.security import evaluate_input, evaluate_output


class GenerationBusyError(RuntimeError):
    pass


class GenerationService:
    def __init__(self, settings, provider):
        self.settings = settings
        self.provider = provider
        self.slots = asyncio.Semaphore(settings.max_concurrent_generations)

    def context(self, history):
        """Keep the newest bounded context without persisting it."""
        selected, count = [], 0
        for item in reversed(history[-self.settings.max_history_messages:]):
            if count + len(item.content) > self.settings.max_history_characters:
                break
            selected.append(item.model_dump())
            count += len(item.content)
        return list(reversed(selected))

    async def generate(self, message, history):
        history = self.context(history)
        decision = evaluate_input(message, self.settings.max_message_length, has_context=bool(history))
        if not decision.allowed:
            return {"answer": decision.answer, "status": decision.status, "safety_reason": decision.reason, "model": None}
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=self.settings.queue_timeout_seconds)
        except TimeoutError as exc:
            raise GenerationBusyError() from exc
        try:
            try:
                async with asyncio.timeout(self.settings.ollama_timeout_seconds):
                    answer, model = await self.provider.chat(message, history)
            except TimeoutError as exc:
                raise OllamaTimeoutError("Generation deadline exceeded") from exc
            decision = evaluate_output(answer, user_message=message, max_words=self.settings.max_response_words)
            return {"answer": decision.answer, "status": decision.status, "safety_reason": decision.reason, "model": model}
        finally:
            self.slots.release()
