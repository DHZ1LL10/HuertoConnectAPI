from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.locks import ConversationLockManager
from app.providers.ollama import OllamaProvider
from app.repository import ConversationRepository
from app.security import evaluate_input, evaluate_output


@dataclass
class ServiceResult:
    answer: str
    conversation_id: str | None
    status: str
    safety_reason: str | None
    model: str | None = None


class ChatService:
    def __init__(
        self,
        settings: Settings,
        provider: OllamaProvider,
        repository: ConversationRepository,
        locks: ConversationLockManager,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.repository = repository
        self.locks = locks

    async def chat(self, user_id: str, message: str, conversation_id: str | None) -> ServiceResult:
        has_context = conversation_id is not None

        # Si el cliente intenta continuar una conversación, validar la propiedad
        # antes de procesar incluso solicitudes bloqueadas o fuera de tema.
        if conversation_id is not None:
            await self.repository.get_owned(conversation_id, user_id)

        input_decision = evaluate_input(
            message,
            self.settings.max_message_length,
            has_context=has_context,
        )
        if not input_decision.allowed:
            return ServiceResult(
                answer=input_decision.answer or "Solicitud bloqueada.",
                conversation_id=conversation_id,
                status=input_decision.status,
                safety_reason=input_decision.reason,
            )

        if conversation_id is None:
            conversation = await self.repository.create(user_id)
            conversation_id = conversation.id

        async with self.locks.get(conversation_id):
            # Verificar nuevamente después de esperar el bloqueo.
            await self.repository.get_owned(conversation_id, user_id)
            history = await self.repository.load_history(
                conversation_id,
                self.settings.max_history_messages,
            )
            raw_answer, model = await self.provider.chat(message, history)
            output_decision = evaluate_output(
                raw_answer,
                user_message=message,
                max_words=self.settings.max_response_words,
            )
            answer = output_decision.answer or "No fue posible generar una respuesta segura."
            await self.repository.add_exchange(conversation_id, message, answer)

        return ServiceResult(
            answer=answer,
            conversation_id=conversation_id,
            status=output_decision.status,
            safety_reason=output_decision.reason,
            model=model,
        )
